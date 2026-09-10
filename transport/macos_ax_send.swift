import AppKit
import ApplicationServices
import CryptoKit
import Dispatch
import Foundation

private enum Exit: Int32 {
    case usage = 2
    case accessibilityDenied = 3
    case chromeUnavailable = 4
    case targetMismatch = 5
    case controlUnavailable = 6
    case pressFailed = 7
    case attachmentUnavailable = 8
    case composerMismatch = 9
    case accessibilityRuntimeUnavailable = 10
}

private func fail(_ code: Exit, _ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(code.rawValue)
}

private func attribute(_ element: AXUIElement, _ name: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name, &value) == .success else {
        return nil
    }
    return value
}

private func stringAttribute(_ element: AXUIElement, _ name: CFString) -> String? {
    guard let value = attribute(element, name) as? String,
          !value.isEmpty else {
        return nil
    }
    return value
}

private func parent(_ element: AXUIElement) -> AXUIElement? {
    guard let raw = attribute(element, kAXParentAttribute as CFString),
          CFGetTypeID(raw) == AXUIElementGetTypeID() else {
        return nil
    }
    return (raw as! AXUIElement)
}

private func boolAttribute(_ element: AXUIElement, _ name: CFString) -> Bool? {
    attribute(element, name) as? Bool
}

private func point(_ element: AXUIElement) -> CGPoint? {
    guard let raw = attribute(element, kAXPositionAttribute as CFString),
          CFGetTypeID(raw) == AXValueGetTypeID() else {
        return nil
    }
    let value = raw as! AXValue
    var result = CGPoint.zero
    guard AXValueGetValue(value, .cgPoint, &result) else { return nil }
    return result
}

private func size(_ element: AXUIElement) -> CGSize? {
    guard let raw = attribute(element, kAXSizeAttribute as CFString),
          CFGetTypeID(raw) == AXValueGetTypeID() else {
        return nil
    }
    let value = raw as! AXValue
    var result = CGSize.zero
    guard AXValueGetValue(value, .cgSize, &result) else { return nil }
    return result
}

private func frame(_ element: AXUIElement) -> CGRect? {
    guard let origin = point(element), let elementSize = size(element),
          origin.x.isFinite, origin.y.isFinite,
          elementSize.width.isFinite, elementSize.height.isFinite,
          elementSize.width > 0, elementSize.height > 0 else {
        return nil
    }
    return CGRect(origin: origin, size: elementSize)
}

private func canonicalChatGPTURL(_ raw: String) -> String? {
    var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if !value.lowercased().hasPrefix("https://") {
        guard !value.contains("://") else { return nil }
        value = "https://" + value
    }
    guard var components = URLComponents(string: value),
          components.scheme?.lowercased() == "https",
          components.host?.lowercased() == "chatgpt.com",
          components.user == nil,
          components.password == nil else {
        return nil
    }
    components.scheme = "https"
    components.host = "chatgpt.com"
    components.fragment = nil
    var path = components.percentEncodedPath
    if path.isEmpty { path = "/" }
    while path.count > 1 && path.hasSuffix("/") { path.removeLast() }
    let query = components.percentEncodedQuery.map { "?" + $0 } ?? ""
    return "https://chatgpt.com\(path)\(query)"
}

private func normalizedText(_ raw: String) -> String {
    raw.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
}

private func normalizedTextSHA256(_ raw: String) -> String {
    SHA256.hash(data: Data(normalizedText(raw).utf8))
        .map { String(format: "%02x", $0) }
        .joined()
}

private func monotonicSeconds() -> Double {
    Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000_000
}

private func attachmentMatches(_ text: String, expectedName: String) -> Bool {
    let file = expectedName as NSString
    let stem = file.deletingPathExtension
    let ext = file.pathExtension
    guard !stem.isEmpty else { return false }
    let escapedStem = NSRegularExpression.escapedPattern(for: stem)
    let escapedExtension = NSRegularExpression.escapedPattern(for: ext)
    let suffix = ext.isEmpty ? "" : "\\.\(escapedExtension)"
    let duplicateToken = "(?:[0-9]+|[0-9]{8}-[0-9]{6})"
    let pattern = "(?:^|\\s)\(escapedStem)(?: ?\\(\(duplicateToken)\\))?\(suffix)(?:\\s|$)"
    return text.range(
        of: pattern,
        options: [.regularExpression]
    ) != nil
}

private enum PressCapability {
    case supported
    case unsupported
    case unreadable
}

private enum ControlLabelRead {
    case label(String)
    case empty
    case unreadable
}

private func pressCapability(_ element: AXUIElement) -> PressCapability {
    var actions: CFArray?
    guard AXUIElementCopyActionNames(element, &actions) == .success,
          let names = actions as? [String] else {
        return .unreadable
    }
    return names.contains(kAXPressAction as String) ? .supported : .unsupported
}

private struct ElementSnapshot {
    let role: String
    let title: String
    let description: String
    let value: String
    let help: String
    let placeholder: String
    let enabled: Bool?
    let hidden: Bool?
    let valueReadable: Bool
    let placeholderReadable: Bool
    let enabledReadable: Bool
    let hiddenReadable: Bool
    let frame: CGRect?
    let children: [AXUIElement]

    var rawSearchableText: String {
        [title, description, value, help]
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }
}

private struct ElementTreeSnapshot {
    let role: String
    let children: [AXUIElement]
}

private func pointValue(_ raw: Any) -> CGPoint? {
    let rawValue = raw as CFTypeRef
    guard CFGetTypeID(rawValue) == AXValueGetTypeID() else { return nil }
    let value = rawValue as! AXValue
    var result = CGPoint.zero
    guard AXValueGetValue(value, .cgPoint, &result) else { return nil }
    return result
}

private func sizeValue(_ raw: Any) -> CGSize? {
    let rawValue = raw as CFTypeRef
    guard CFGetTypeID(rawValue) == AXValueGetTypeID() else { return nil }
    let value = rawValue as! AXValue
    var result = CGSize.zero
    guard AXValueGetValue(value, .cgSize, &result) else { return nil }
    return result
}

private func elementSnapshot(_ element: AXUIElement) -> ElementSnapshot? {
    let names: [CFString] = [
        kAXRoleAttribute as CFString,
        kAXTitleAttribute as CFString,
        kAXDescriptionAttribute as CFString,
        kAXValueAttribute as CFString,
        kAXHelpAttribute as CFString,
        kAXPlaceholderValueAttribute as CFString,
        kAXEnabledAttribute as CFString,
        kAXHiddenAttribute as CFString,
        kAXPositionAttribute as CFString,
        kAXSizeAttribute as CFString,
        kAXChildrenAttribute as CFString,
    ]
    var rawValues: CFArray?
    guard AXUIElementCopyMultipleAttributeValues(
        element,
        names as CFArray,
        AXCopyMultipleAttributeOptions(rawValue: 0),
        &rawValues
    ) == .success,
    let values = rawValues as? [Any],
    values.count == names.count else {
        return nil
    }
    let origin = pointValue(values[8])
    let elementSize = sizeValue(values[9])
    var elementFrame: CGRect?
    if let origin, let elementSize,
       origin.x.isFinite, origin.y.isFinite,
       elementSize.width.isFinite, elementSize.height.isFinite,
       elementSize.width > 0, elementSize.height > 0 {
        elementFrame = CGRect(origin: origin, size: elementSize)
    }
    return ElementSnapshot(
        role: (values[0] as? String) ?? "",
        title: (values[1] as? String) ?? "",
        description: (values[2] as? String) ?? "",
        value: (values[3] as? String) ?? "",
        help: (values[4] as? String) ?? "",
        placeholder: (values[5] as? String) ?? "",
        enabled: values[6] as? Bool,
        hidden: values[7] as? Bool,
        valueReadable: values[3] is String,
        placeholderReadable: values[5] is String,
        enabledReadable: values[6] is Bool,
        hiddenReadable: values[7] is Bool,
        frame: elementFrame,
        children: (values[10] as? [AXUIElement]) ?? []
    )
}

private func elementTreeSnapshot(_ element: AXUIElement) -> ElementTreeSnapshot? {
    let names: [CFString] = [
        kAXRoleAttribute as CFString,
        kAXChildrenAttribute as CFString,
    ]
    var rawValues: CFArray?
    guard AXUIElementCopyMultipleAttributeValues(
        element,
        names as CFArray,
        AXCopyMultipleAttributeOptions(rawValue: 0),
        &rawValues
    ) == .success,
    let values = rawValues as? [Any],
    values.count == names.count else {
        return nil
    }
    guard let role = values[0] as? String, !role.isEmpty else {
        return nil
    }
    let knownLeafRoles: Set<String> = [
        kAXButtonRole as String,
        kAXCheckBoxRole as String,
        kAXImageRole as String,
        "AXLink",
        kAXRadioButtonRole as String,
        kAXStaticTextRole as String,
        kAXTextAreaRole as String,
        kAXTextFieldRole as String,
    ]
    let resolvedChildren: [AXUIElement]
    if let children = values[1] as? [AXUIElement] {
        resolvedChildren = children
    } else if knownLeafRoles.contains(role) {
        resolvedChildren = []
    } else {
        return nil
    }
    return ElementTreeSnapshot(
        role: role,
        children: resolvedChildren
    )
}

private func controlLabel(_ element: AXUIElement) -> ControlLabelRead {
    let names: [CFString] = [
        kAXTitleAttribute as CFString,
        kAXDescriptionAttribute as CFString,
        kAXValueAttribute as CFString,
        kAXHelpAttribute as CFString,
    ]
    var rawValues: CFArray?
    guard AXUIElementCopyMultipleAttributeValues(
        element,
        names as CFArray,
        AXCopyMultipleAttributeOptions(rawValue: 0),
        &rawValues
    ) == .success,
    let values = rawValues as? [Any],
    values.count == names.count else {
        return .unreadable
    }
    var parts: [String] = []
    for raw in values {
        if let value = raw as? String {
            if !value.isEmpty { parts.append(value) }
            continue
        }
        let rawValue = raw as CFTypeRef
        if CFGetTypeID(rawValue) == CFNullGetTypeID() {
            continue
        }
        guard CFGetTypeID(rawValue) == AXValueGetTypeID() else {
            return .unreadable
        }
        let value = rawValue as! AXValue
        guard AXValueGetType(value) == .axError else {
            return .unreadable
        }
        var error = AXError.success
        guard AXValueGetValue(value, .axError, &error) else {
            return .unreadable
        }
        guard error == .noValue || error == .attributeUnsupported else {
            return .unreadable
        }
    }
    let label = parts.joined(separator: " ")
    return label.isEmpty ? .empty : .label(label)
}

private func visibleEnabledElement(
    snapshot: ElementSnapshot
) -> Bool? {
    guard snapshot.enabledReadable,
          snapshot.hiddenReadable else {
        return nil
    }
    guard snapshot.enabled == true,
          snapshot.hidden == false,
          snapshot.frame != nil else {
        return false
    }
    return true
}

private func visibleEnabledButton(
    _ element: AXUIElement,
    snapshot: ElementSnapshot
) -> Bool? {
    guard let visible = visibleEnabledElement(snapshot: snapshot) else {
        return nil
    }
    guard visible else { return false }
    switch pressCapability(element) {
    case .supported:
        return true
    case .unsupported:
        return false
    case .unreadable:
        return nil
    }
}

private func visibleAttachmentGroup(
    snapshot: ElementSnapshot
) -> Bool? {
    guard let groupFrame = snapshot.frame,
          groupFrame.width > 0,
          groupFrame.height > 0 else {
        return false
    }
    if snapshot.hiddenReadable, snapshot.hidden == true {
        return false
    }
    // ChatGPT's image tile is a passive AXGroup and may legitimately omit
    // AXEnabled/AXHidden values. Its frame plus the focused web-area scope
    // are the visibility contract; the send control remains strictly gated.
    return true
}

private func ancestorChain(
    _ element: AXUIElement,
    maximumDepth: Int = 16
) -> [AXUIElement] {
    var chain: [AXUIElement] = [element]
    var current = element
    for _ in 0..<maximumDepth {
        guard let next = parent(current) else { break }
        if chain.contains(where: { CFEqual($0, next) }) { break }
        chain.append(next)
        current = next
    }
    return chain
}

private func lowestCommonAncestor(
    _ elements: [AXUIElement]
) -> AXUIElement? {
    guard let first = elements.first else { return nil }
    let chains = elements.map { ancestorChain($0) }
    for candidate in ancestorChain(first) {
        if chains.dropFirst().allSatisfy({ chain in
            chain.contains(where: { CFEqual($0, candidate) })
        }) {
            return candidate
        }
    }
    return nil
}

struct TargetInspection {
    let window: AXUIElement
    let addressMatches: Bool
    let attachmentMatches: Bool
    let composerMatches: Bool
    let attachmentCount: Int
    let composerCount: Int
    let sendButtonCount: Int
    let scanCompleted: Bool
    let sendButton: AXUIElement?
    let visitedCount: Int
    let snapshotCount: Int
    let textFieldCount: Int
    let addressFieldCount: Int
    let addressMatchCount: Int
    let textAreaCount: Int
    let buttonCount: Int
    let composerSharesSendParent: Bool
    let attachmentSharesComposerGroup: Bool
    let controlFramesAvailable: Bool
    let controlsInsideWindow: Bool
    let controlsVerticallyAligned: Bool
}

struct TargetCandidate {
    let chrome: NSRunningApplication
    let app: AXUIElement
    let inspection: TargetInspection
}

struct ChromeTarget {
    let chrome: NSRunningApplication
    let app: AXUIElement
}

private struct TraversalEntry {
    let element: AXUIElement
    let insideWebArea: Bool
    let insideToolbar: Bool
    let insideFocusedWebArea: Bool
}

private func applicationWindows(_ app: AXUIElement) -> [AXUIElement]? {
    guard let raw = attribute(app, kAXWindowsAttribute as CFString) else {
        return nil
    }
    return raw as? [AXUIElement]
}

private func focusedWebArea(_ app: AXUIElement) -> AXUIElement? {
    guard let raw = attribute(app, kAXFocusedUIElementAttribute as CFString),
          CFGetTypeID(raw) == AXUIElementGetTypeID() else {
        return nil
    }
    var current = raw as! AXUIElement
    for _ in 0..<24 {
        if stringAttribute(current, kAXRoleAttribute as CFString) == "AXWebArea" {
            return current
        }
        guard let next = parent(current) else { break }
        current = next
    }
    return nil
}

private func sameFrame(_ lhs: CGRect?, _ rhs: CGRect?) -> Bool {
    guard let lhs, let rhs else { return false }
    return abs(lhs.minX - rhs.minX) < 0.5
        && abs(lhs.minY - rhs.minY) < 0.5
        && abs(lhs.width - rhs.width) < 0.5
        && abs(lhs.height - rhs.height) < 0.5
}

private func inspectTarget(
    window: AXUIElement,
    focusedContent: AXUIElement?,
    expectedURL: String,
    expectedName: String,
    expectedTextSHA256: String,
    scanDeadline: Double
) -> TargetInspection {
    var queue = [TraversalEntry(
        element: window,
        insideWebArea: false,
        insideToolbar: false,
        insideFocusedWebArea: false
    )]
    var cursor = 0
    var visited = 0
    var addressMatchCount = 0
    var scanCompleted = true
    var visitedElements: [CFHashCode: [AXUIElement]] = [:]
    var snapshotCount = 0
    var textFieldCount = 0
    var addressFieldCount = 0
    var textAreaCount = 0
    var buttonCount = 0
    let focusedContentFrame = focusedContent.flatMap(frame)
    var composerElements: [AXUIElement] = []
    var attachmentButtons: [AXUIElement] = []
    var attachmentGroups: [AXUIElement] = []
    var sendButtons: [AXUIElement] = []
    guard let windowFrame = frame(window) else {
        return TargetInspection(
            window: window,
            addressMatches: false,
            attachmentMatches: false,
            composerMatches: false,
            attachmentCount: 0,
            composerCount: 0,
            sendButtonCount: 0,
            scanCompleted: false,
            sendButton: nil,
            visitedCount: 0,
            snapshotCount: 0,
            textFieldCount: 0,
            addressFieldCount: 0,
            addressMatchCount: 0,
            textAreaCount: 0,
            buttonCount: 0,
            composerSharesSendParent: false,
            attachmentSharesComposerGroup: false,
            controlFramesAvailable: false,
            controlsInsideWindow: false,
            controlsVerticallyAligned: false
        )
    }

    scanLoop: while cursor < queue.count && visited < 20_000 {
        if monotonicSeconds() >= scanDeadline {
            scanCompleted = false
            break
        }
        let entry = queue[cursor]
        let element = entry.element
        cursor += 1
        let elementHash = CFHash(element)
        let hashMatches = visitedElements[elementHash] ?? []
        if hashMatches.contains(where: { CFEqual($0, element) }) { continue }
        visitedElements[elementHash, default: []].append(element)
        visited += 1
        guard let tree = elementTreeSnapshot(element) else {
            scanCompleted = false
            break
        }
        let role = tree.role
        let descendantsAreInsideWebArea = entry.insideWebArea || role == "AXWebArea"
        let descendantsAreInsideToolbar = entry.insideToolbar
            || role == (kAXToolbarRole as String)
        let isFocusedContentRoot = role == "AXWebArea"
            && (focusedContent.map { CFEqual($0, element) } == true
                || sameFrame(frame(element), focusedContentFrame))
        let descendantsAreInsideFocusedWebArea = entry.insideFocusedWebArea
            || isFocusedContentRoot
        queue.append(contentsOf: tree.children.map {
            TraversalEntry(
                element: $0,
                insideWebArea: descendantsAreInsideWebArea,
                insideToolbar: descendantsAreInsideToolbar,
                insideFocusedWebArea: descendantsAreInsideFocusedWebArea
            )
        })

        if role == (kAXTextFieldRole as String) {
            guard let snapshot = elementSnapshot(element) else {
                scanCompleted = false
                break
            }
            snapshotCount += 1
            textFieldCount += 1
            let text = snapshot.rawSearchableText
                .folding(
                    options: [.diacriticInsensitive, .caseInsensitive],
                    locale: .current
                )
                .lowercased()
            let addressField = text.contains("address and search bar")
                || text.contains("barre d'adresse et de recherche")
                || text.contains("barre d’adresse et de recherche")
            let addressFrameIsVisible = snapshot.valueReadable
                && snapshot.enabledReadable
                && snapshot.hiddenReadable
                && snapshot.enabled == true
                && snapshot.hidden == false
                && snapshot.frame.map { fieldFrame in
                    fieldFrame.width >= 200
                        && fieldFrame.height > 0
                        && fieldFrame.height <= 80
                        && windowFrame.contains(CGPoint(
                            x: fieldFrame.midX,
                            y: fieldFrame.midY
                        ))
                } == true
            if addressField,
               entry.insideToolbar,
               !entry.insideWebArea,
               addressFrameIsVisible {
                addressFieldCount += 1
                if canonicalChatGPTURL(snapshot.value) == expectedURL {
                    addressMatchCount += 1
                }
            }
        }
        if role == (kAXTextAreaRole as String) {
            guard entry.insideFocusedWebArea else { continue }
            guard let snapshot = elementSnapshot(element) else {
                scanCompleted = false
                break
            }
            guard snapshot.valueReadable,
                  snapshot.enabledReadable,
                  snapshot.hiddenReadable,
                  snapshot.enabled == true,
                  snapshot.hidden == false,
                  snapshot.frame != nil else {
                continue
            }
            snapshotCount += 1
            textAreaCount += 1
            let value = normalizedText(snapshot.value)
            let placeholder = normalizedText(snapshot.placeholder)
            let normalizedValue = value.folding(
                options: [.diacriticInsensitive, .caseInsensitive],
                locale: .current
            ).lowercased()
            let knownEmptyComposerValue = [
                "demander a chatgpt",
                "discuter avec chatgpt",
            ].contains(normalizedValue)
            let placeholderRepresentsEmpty = (
                snapshot.placeholderReadable
                    && !placeholder.isEmpty
                    && value == placeholder
            ) || knownEmptyComposerValue
            let effectiveValue = value.isEmpty || placeholderRepresentsEmpty
                ? ""
                : value
            let matches = normalizedTextSHA256(effectiveValue)
                == expectedTextSHA256
            if matches { composerElements.append(element) }
        }
        if role == (kAXButtonRole as String) {
            guard entry.insideFocusedWebArea else { continue }
            buttonCount += 1
            let labelRead = controlLabel(element)
            let rawText: String
            switch labelRead {
            case let .label(value):
                rawText = value
            case .empty:
                continue
            case .unreadable:
                scanCompleted = false
                break scanLoop
            }
            let text = rawText
                .folding(
                    options: [.diacriticInsensitive, .caseInsensitive],
                    locale: .current
                )
                .lowercased()
            let isSendLabel = text.contains("send prompt")
                || text.contains("envoyer le prompt")
            let isAttachmentLabel = !text.contains("remove file")
                && !text.contains("supprimer le fichier")
                && attachmentMatches(rawText, expectedName: expectedName)
            guard isSendLabel || isAttachmentLabel else {
                continue
            }
            guard let snapshot = elementSnapshot(element) else {
                scanCompleted = false
                break
            }
            snapshotCount += 1
            guard let isVisibleEnabledButton = visibleEnabledButton(
                element,
                snapshot: snapshot
            ) else {
                scanCompleted = false
                break
            }
            if isVisibleEnabledButton, isAttachmentLabel {
                attachmentButtons.append(element)
            }
            if isVisibleEnabledButton, isSendLabel {
                sendButtons.append(element)
            }
        }
        if role == (kAXGroupRole as String), entry.insideWebArea {
            guard entry.insideFocusedWebArea else { continue }
            let labelRead = controlLabel(element)
            let rawText: String
            switch labelRead {
            case let .label(value):
                rawText = value
            case .empty:
                continue
            case .unreadable:
                scanCompleted = false
                break scanLoop
            }
            guard attachmentMatches(rawText, expectedName: expectedName) else {
                continue
            }
            guard let snapshot = elementSnapshot(element),
                  let isVisibleGroup = visibleAttachmentGroup(snapshot: snapshot) else {
                scanCompleted = false
                break
            }
            snapshotCount += 1
            if isVisibleGroup {
                attachmentGroups.append(element)
            }
        }
    }

    if cursor < queue.count { scanCompleted = false }

    let sendButton = sendButtons.count == 1 ? sendButtons[0] : nil
    let composer = composerElements.count == 1 ? composerElements[0] : nil
    let attachmentCandidates = attachmentButtons.isEmpty ? attachmentGroups : attachmentButtons
    let attachment = attachmentCandidates.count == 1 ? attachmentCandidates[0] : nil
    var composerSharesSendParent = false
    var attachmentSharesComposerGroup = false
    var controlFramesAvailable = false
    var controlsInsideWindow = false
    var controlsVerticallyAligned = false
    let attachmentIsInComposer = {
        guard let sendButton, let composer, let attachment,
              let sendParent = parent(sendButton),
              let composerParent = parent(composer),
              sameWindow(sendParent, composerParent),
              let commonComposerAncestor = lowestCommonAncestor([
                  sendButton,
                  composer,
                  attachment,
              ]),
              let sendFrame = frame(sendButton),
              let composerFrame = frame(composer),
              let attachmentFrame = frame(attachment),
              let groupFrame = frame(commonComposerAncestor) else {
            return false
        }
        composerSharesSendParent = true
        controlFramesAvailable = true
        guard let commonAncestorRole = stringAttribute(
            commonComposerAncestor,
            kAXRoleAttribute as CFString
        ) else {
            return false
        }
        let commonAncestorIsAComposerGroup = commonAncestorRole != "AXWebArea"
            && commonAncestorRole != (kAXWindowRole as String)
        let groupFrameIsBounded = commonAncestorIsAComposerGroup
            && groupFrame.height <= 420
            && groupFrame.height <= windowFrame.height * 0.55
            && groupFrame.width <= windowFrame.width + 1
        let geometricComposerGroup = groupFrameIsBounded
            && groupFrame.contains(CGPoint(
                x: sendFrame.midX,
                y: sendFrame.midY
            )) && groupFrame.contains(CGPoint(
                x: composerFrame.midX,
                y: composerFrame.midY
            )) && groupFrame.contains(CGPoint(
                x: attachmentFrame.midX,
                y: attachmentFrame.midY
            ))
        attachmentSharesComposerGroup = geometricComposerGroup
        let allInsideWindow = windowFrame.contains(CGPoint(
            x: sendFrame.midX, y: sendFrame.midY
        )) && windowFrame.contains(CGPoint(
            x: composerFrame.midX, y: composerFrame.midY
        )) && windowFrame.contains(CGPoint(
            x: attachmentFrame.midX, y: attachmentFrame.midY
        ))
        controlsInsideWindow = allInsideWindow
        let verticallyAligned = abs(attachmentFrame.midY - sendFrame.midY) <= 220
            && abs(composerFrame.midY - sendFrame.midY) <= 180
        controlsVerticallyAligned = verticallyAligned
        return geometricComposerGroup
            && allInsideWindow
            && verticallyAligned
    }()
    return TargetInspection(
        window: window,
        addressMatches: addressMatchCount == 1,
        attachmentMatches: attachmentIsInComposer,
        composerMatches: composerElements.count == 1,
        attachmentCount: attachmentCandidates.count,
        composerCount: composerElements.count,
        sendButtonCount: sendButtons.count,
        scanCompleted: scanCompleted,
        sendButton: sendButton,
        visitedCount: visited,
        snapshotCount: snapshotCount,
        textFieldCount: textFieldCount,
        addressFieldCount: addressFieldCount,
        addressMatchCount: addressMatchCount,
        textAreaCount: textAreaCount,
        buttonCount: buttonCount,
        composerSharesSendParent: composerSharesSendParent,
        attachmentSharesComposerGroup: attachmentSharesComposerGroup,
        controlFramesAvailable: controlFramesAvailable,
        controlsInsideWindow: controlsInsideWindow,
        controlsVerticallyAligned: controlsVerticallyAligned
    )
}

private func isExactTarget(_ inspection: TargetInspection) -> Bool {
    inspection.scanCompleted
        && inspection.addressMatches
        && inspection.addressFieldCount == 1
        && inspection.addressMatchCount == 1
        && inspection.attachmentMatches
        && inspection.composerMatches
        && inspection.attachmentCount == 1
        && inspection.composerCount == 1
        && inspection.sendButtonCount == 1
        && inspection.sendButton != nil
}

private func sameWindow(_ lhs: AXUIElement, _ rhs: AXUIElement) -> Bool {
    CFEqual(lhs, rhs)
}

private func scanCandidates(
    chromeTargets: [ChromeTarget],
    expectedURL: String,
    expectedName: String,
    expectedTextSHA256: String,
    scanDeadline: Double
) -> (
    inspections: [TargetInspection],
    candidates: [TargetCandidate],
    complete: Bool
) {
    var inspections: [TargetInspection] = []
    var candidates: [TargetCandidate] = []
    var complete = true
    for target in chromeTargets {
        guard monotonicSeconds() < scanDeadline,
              let windows = applicationWindows(target.app) else {
            complete = false
            break
        }
        for window in windows {
            let focusedContent = focusedWebArea(target.app)
            let inspection = inspectTarget(
                window: window,
                focusedContent: focusedContent,
                expectedURL: expectedURL,
                expectedName: expectedName,
                expectedTextSHA256: expectedTextSHA256,
                scanDeadline: scanDeadline
            )
            inspections.append(inspection)
            if !inspection.scanCompleted { complete = false }
            if isExactTarget(inspection) {
                candidates.append(TargetCandidate(
                    chrome: target.chrome,
                    app: target.app,
                    inspection: inspection
                ))
            }
            if monotonicSeconds() >= scanDeadline {
                complete = false
                break
            }
        }
        if !complete { break }
    }
    return (inspections, candidates, complete)
}

if CommandLine.arguments == [CommandLine.arguments[0], "--check-permissions"] {
    guard AXIsProcessTrusted() else {
        fail(.accessibilityDenied, "macOS Accessibility permission is required")
    }
    print("READY")
    exit(0)
}
guard CommandLine.arguments.count == 1 else {
    fail(.usage, "usage: cortex-macos-ax-send < JSON request on stdin")
}
guard AXIsProcessTrusted() else {
    fail(.accessibilityDenied, "macOS Accessibility permission is required")
}
let systemWideAccessibility = AXUIElementCreateSystemWide()
guard AXUIElementSetMessagingTimeout(systemWideAccessibility, 0.25) == .success else {
    fail(.accessibilityRuntimeUnavailable, "the accessibility timeout could not be bounded")
}
guard let input = try? FileHandle.standardInput.read(upToCount: 65_537),
      input.count <= 65_536 else {
    fail(.usage, "invalid activation request")
}
guard input.count <= 65_536,
      let request = try? JSONSerialization.jsonObject(with: input) as? [String: Any],
      let requestedURL = request["expected_url"] as? String,
      let requestedName = request["expected_file_name"] as? String,
      let requestedTextSHA256 = request["expected_text_sha256"] as? String,
      requestedName.count <= 255,
      !requestedName.isEmpty,
      requestedTextSHA256.count == 64,
      requestedTextSHA256.allSatisfy({ character in
          let value = String(character)
          return ("0"..."9").contains(value)
              || ("a"..."f").contains(value)
      }),
      (requestedName as NSString).lastPathComponent == requestedName,
      let parsedURL = URL(string: requestedURL),
      parsedURL.scheme == "https",
      parsedURL.host == "chatgpt.com",
      parsedURL.user == nil,
      parsedURL.password == nil else {
    fail(.usage, "invalid activation request")
}
let chromeApplications = NSRunningApplication.runningApplications(
    withBundleIdentifier: "com.google.Chrome"
)
guard !chromeApplications.isEmpty else {
    fail(.chromeUnavailable, "Google Chrome is not running")
}
let chromeTargets = chromeApplications.map { chrome in
    let app = AXUIElementCreateApplication(chrome.processIdentifier)
    return ChromeTarget(
        chrome: chrome,
        app: app
    )
}
guard let expectedURL = canonicalChatGPTURL(requestedURL) else {
    fail(.usage, "invalid ChatGPT activation URL")
}
let expectedName = requestedName
let expectedTextSHA256 = requestedTextSHA256
let discoveryDeadline = monotonicSeconds() + 5.0
var latestInspections: [TargetInspection] = []
var verifiedCandidate: TargetCandidate?
var consecutiveMatches = 0

repeat {
    let scan = scanCandidates(
        chromeTargets: chromeTargets,
        expectedURL: expectedURL,
        expectedName: expectedName,
        expectedTextSHA256: expectedTextSHA256,
        scanDeadline: discoveryDeadline
    )
    if scan.inspections.contains(where: { $0.visitedCount > 0 }) {
        latestInspections = scan.inspections
    }
    let candidates = scan.candidates
    if scan.complete, candidates.count == 1 {
        let candidate = candidates[0]
        if let previous = verifiedCandidate,
           previous.chrome.processIdentifier == candidate.chrome.processIdentifier,
           sameWindow(previous.inspection.window, candidate.inspection.window) {
            consecutiveMatches += 1
        } else {
            consecutiveMatches = 1
        }
        verifiedCandidate = candidate
        if consecutiveMatches >= 2 { break }
    } else {
        consecutiveMatches = 0
        verifiedCandidate = nil
    }
    if monotonicSeconds() >= discoveryDeadline { break }
    Thread.sleep(forTimeInterval: 0.05)
} while true

guard let verifiedCandidate, consecutiveMatches >= 2 else {
    let addressTargets = latestInspections.filter(\.addressMatches)
    guard !addressTargets.isEmpty else {
        fail(.targetMismatch, "no Chrome window exposes the prepared ChatGPT URL")
    }
    guard addressTargets.contains(where: { $0.sendButtonCount == 1 }) else {
        fail(.controlUnavailable, "the exact ChatGPT send control is not uniquely available")
    }
    guard addressTargets.contains(where: \.attachmentMatches) else {
        fail(.attachmentUnavailable, "the prepared attachment is not visible beside the ChatGPT send control")
    }
    guard addressTargets.contains(where: \.composerMatches) else {
        fail(.composerMismatch, "the visible ChatGPT composer does not match the prepared message")
    }
    fail(.targetMismatch, "the prepared ChatGPT target is ambiguous or unstable")
}

let chrome = verifiedCandidate.chrome
let app = verifiedCandidate.app
let targetWindow = verifiedCandidate.inspection.window
guard chrome.activate(options: []) else {
    fail(.chromeUnavailable, "Google Chrome could not be activated")
}
guard AXUIElementPerformAction(
    targetWindow,
    kAXRaiseAction as CFString
) == .success else {
    fail(.chromeUnavailable, "the verified Chrome window could not be raised")
}

let focusDeadline = monotonicSeconds() + 2.5
var focusedInspection: TargetInspection?
var focusedMatches = 0
repeat {
    let currentWindow = attribute(app, kAXFocusedWindowAttribute as CFString)
    let windowMatches = currentWindow.map {
        CFGetTypeID($0) == AXUIElementGetTypeID() && CFEqual($0, targetWindow)
    } ?? false
    let targetIsMain = boolAttribute(
        targetWindow,
        kAXMainAttribute as CFString
    ) == true
    let scan = scanCandidates(
        chromeTargets: chromeTargets,
        expectedURL: expectedURL,
        expectedName: expectedName,
        expectedTextSHA256: expectedTextSHA256,
        scanDeadline: focusDeadline
    )
    let uniqueCandidate = scan.complete && scan.candidates.count == 1
        ? scan.candidates[0]
        : nil
    let exactWindowRemains = uniqueCandidate.map {
        $0.chrome.processIdentifier == chrome.processIdentifier
            && CFEqual($0.inspection.window, targetWindow)
    } ?? false
    if windowMatches, targetIsMain, exactWindowRemains,
       let uniqueCandidate {
        focusedMatches += 1
        focusedInspection = uniqueCandidate.inspection
        if focusedMatches >= 2 { break }
    } else {
        focusedMatches = 0
        focusedInspection = nil
    }
    if monotonicSeconds() >= focusDeadline { break }
    Thread.sleep(forTimeInterval: 0.05)
} while true

guard let focusedInspection,
      focusedMatches >= 2,
      let sendButton = focusedInspection.sendButton else {
    fail(.targetMismatch, "the verified Chrome target did not remain focused")
}
guard AXUIElementPerformAction(
    sendButton,
    kAXPressAction as CFString
) == .success else {
    fail(.pressFailed, "macOS could not press the verified ChatGPT send control")
}

print("PRESS_STARTED")
