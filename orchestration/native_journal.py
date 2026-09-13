"""Native-host handoff backed by the existing Store, not a new transport.

The host must supply actual read-tool observations. This module cannot attest
their origin, call desktop tools, or turn an operator declaration into proof.
"""
import hashlib
import json
import uuid

from .store import Store, StoreError, TERMINAL_STATES
from .protocol import DecisionError, validate_decision


def _bound(store: Store, mission_id: str, conversation_id: str) -> None:
    store.get_mission(mission_id)
    bindings = store.rows("conversation_bindings", mission_id)
    if len(bindings) != 1 or bindings[0]["conversation_url"] != f"https://chatgpt.com/c/{conversation_id}":
        raise StoreError("native conversation binding mismatch")


def prepare(store: Store, mission_id: str, conversation_id: str,
            before_message_id: str, message: str, *, _context: dict | None = None) -> dict:
    """Reserve before native send; return technical wire text, never send it."""
    _bound(store, mission_id, conversation_id)
    store.check_native_deadline(mission_id)
    state = store.get_mission(mission_id)["state"]
    if state in TERMINAL_STATES or state.startswith("PAUSED"):
        raise StoreError("mission stopped or paused; native send prohibited")
    if (not isinstance(before_message_id, str) or not before_message_id
            or before_message_id.startswith("idx-") or not isinstance(message, str)
            or not message or len(message.encode("utf-8")) > 1_000_000):
        raise StoreError("invalid native checkpoint or message")
    send_id = str(uuid.uuid4())
    checkpoint = {"conversation_id": conversation_id, "last_message_id": before_message_id,
                  "channel": "native_host"}
    if _context is not None:
        checkpoint["context"] = _context
    digest = store.reserve_outbound(send_id, mission_id, message, checkpoint=checkpoint)
    return {"state": "prepared", "send_id": send_id, "sha256": digest,
            "message": message + f"\n\n[cortex-transport send_id={send_id}]"}


def define_acceptance(store: Store, mission_id: str, criteria: list[dict]) -> dict:
    return store.define_native_acceptance(mission_id, criteria)


def check_acceptance_evidence(store: Store, mission_id: str, evidence: list[dict]) -> dict:
    """Check coverage and recorded proof bytes, not semantic test adequacy."""
    from pathlib import Path
    from .artifacts import MAX_TOTAL, verify_sources
    mission = store.get_mission(mission_id)
    baselines = [json.loads(e["detail_json"]) for e in store.rows("transport_events", mission_id)
                 if e["event_type"] == "NATIVE_ACCEPTANCE_DEFINED"]
    if len(baselines) != 1:
        raise StoreError("one frozen acceptance baseline required")
    expected = {c["id"] for c in baselines[0]["criteria"]}
    if (not isinstance(evidence, list) or len(evidence) != len(expected)
            or any(not isinstance(e, dict) or set(e) != {"criterion_id", "verdict", "record_id"}
                   or not isinstance(e["criterion_id"], str) or not isinstance(e["record_id"], str)
                   or e["verdict"] not in {"PASS", "FAIL", "UNCLEAR"} for e in evidence)
            or {e["criterion_id"] for e in evidence} != expected):
        raise StoreError("acceptance evidence must cover every criterion exactly once")
    if store.unresolved_outbound(mission_id) or store.pending_native_actions(mission_id):
        raise StoreError("pending work requires reconciliation before evidence review")
    records = {r["id"]: r for r in store.rows("tool_executions", mission_id)}
    checks = []
    total = 0
    for entry in evidence:
        row = records.get(entry["record_id"])
        if row is None or row["finished_at"] is None or not row["tool"].startswith("native:"):
            raise StoreError("criterion requires a completed native record from this mission")
        receipt = json.loads(row["result_json"])
        kind = receipt.get("receipt_kind")
        if kind not in {"process", "host_tool"}:
            raise StoreError("unknown evidence receipt kind")
        successful = receipt.get("outcome") == "succeeded"
        if kind == "process":
            successful = successful and row["exit_code"] == 0
        if entry["verdict"] == "PASS" and not successful:
            raise StoreError("failed action cannot support reported PASS")
        details = receipt.get("evidence" if kind == "process" else "verification")
        manifest = details.get("proof_manifest") if isinstance(details, dict) else None
        if not isinstance(manifest, dict) or not isinstance(manifest.get("items"), list):
            raise StoreError("proof manifest must be retained in original action receipt")
        for item in manifest["items"]:
            if not isinstance(item, dict) or type(item.get("bytes")) is not int or item["bytes"] < 0:
                raise StoreError("invalid proof size")
            total += item["bytes"]
        if total > MAX_TOTAL:
            raise StoreError("acceptance proof read budget exceeded")
        verified = verify_sources(Path(mission["workspace"]), manifest)
        checks.append({**entry, "proof_selection_sha256": verified["selection_sha256"],
                       "receipt_sha256": hashlib.sha256(row["result_json"].encode()).hexdigest()})
    verdicts = {e["verdict"] for e in evidence}
    reported = "FAIL" if "FAIL" in verdicts else "UNCLEAR" if "UNCLEAR" in verdicts else "PASS"
    return {"state": "acceptance_evidence_checked", "evidence_integrity": "PASS",
            "reported_acceptance": reported, "acceptance_sha256": baselines[0]["acceptance_sha256"],
            "criteria": checks, "completion_verified": False, "semantic_review_required": True,
            "evidence_source": "host_observation_supplied"}


def prepare_context(store: Store, mission_id: str, conversation_id: str,
                    before_message_id: str, message: str, manifest: dict) -> dict:
    """Freeze the verified selection reference in both wire text and reservation.

    Files are still NOT delivered by this operation. Supplied metadata does not
    become an approval, and no assistant decision has yet been validated.
    """
    from pathlib import Path
    from .artifacts import verify_sources
    _bound(store, mission_id, conversation_id)
    mission = store.get_mission(mission_id)
    if mission["state"] in TERMINAL_STATES or mission["state"].startswith("PAUSED"):
        raise StoreError("mission stopped or paused")
    store.check_native_deadline(mission_id)
    if not isinstance(message, str) or not message or len(message.encode()) > 900_000:
        raise StoreError("invalid context message")
    verified = verify_sources(Path(mission["workspace"]), manifest)
    # Only validated metadata is retained; do not forward arbitrary manifest
    # extensions, claimed delivery fields, or an untrusted context packet.
    selection = {"protocol": "cortex-artifacts.v1", "items": [
        {key: item[key] for key in ("path", "bytes", "sha256")}
        for item in manifest["items"]]}
    context = {"selection_sha256": verified["selection_sha256"],
               "manifest": selection, "delivery_verified": False}
    baselines = [json.loads(e["detail_json"]) for e in store.rows("transport_events", mission_id)
                 if e["event_type"] == "NATIVE_ACCEPTANCE_DEFINED"]
    if baselines:
        if len(baselines) != 1:
            raise StoreError("ambiguous acceptance contract")
        context["acceptance"] = baselines[0]
    wire = (message + "\n\nCortex selected-source context reference:\n"
            + json.dumps(context, sort_keys=True, ensure_ascii=False)
            + "\nThese are source references, not file contents or delivery proof. "
              "Request missing contents before making decisions. Return only a JSON object with "
              "exactly selection_sha256 and decision. decision must follow cortex.v1, "
            + f"missionId={mission_id}, iteration={mission['iteration'] + 1}. "
              "Cite the exact selection_sha256. A COMPLETE decision is only a proposal for local validation.")
    return prepare(store, mission_id, conversation_id, before_message_id, wire, _context=context)


def check_context_reply(store: Store, mission_id: str, first: dict, second: dict) -> dict:
    """Read-only observed reply check; never authorizes effects or completion."""
    from pathlib import Path
    from .artifacts import verify_sources
    if store.unresolved_outbound(mission_id) is not None:
        raise StoreError("outbound receipt unresolved")
    events = store.rows("transport_events", mission_id, order_by="rowid")
    starts = [e for e in events if e["event_type"] == "MESSAGE_SEND_STARTED"]
    if not starts:
        raise StoreError("no context request")
    request = starts[-1]
    detail = json.loads(request["detail_json"])
    checkpoint = detail.get("checkpoint") or {}
    context = checkpoint.get("context")
    if checkpoint.get("channel") != "native_host" or not isinstance(context, dict):
        raise StoreError("latest request has no native context binding")
    _bound(store, mission_id, checkpoint["conversation_id"])
    deliveries = [json.loads(e["detail_json"]) for e in events
                  if e["event_type"] == "MESSAGE_DELIVERED"
                  and json.loads(e["detail_json"]).get("send_id") == request["id"]]
    if len(deliveries) != 1:
        raise StoreError("request delivery not uniquely confirmed")
    delivery = deliveries[0]
    suffix = f"\n\n[cortex-transport send_id={request['id']}]"

    def observed(snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("conversation_id") != checkpoint["conversation_id"]:
            raise StoreError("reply conversation mismatch")
        messages = snapshot.get("messages")
        if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
            raise StoreError("invalid reply observation")
        anchors = [i for i, m in enumerate(messages) if m.get("id") == delivery.get("message_id")]
        if len(anchors) != 1 or anchors[0] != len(messages) - 2:
            raise StoreError("reply must immediately follow confirmed request")
        user, reply = messages[-2:]
        text = user.get("text")
        if user.get("role") != "user" or not isinstance(text, str):
            raise StoreError("invalid observed request")
        raw = delivery.get("raw_receipt")
        if raw is not None:
            matches = text == raw.get("text")
        else:
            matches = text.endswith(suffix) and hashlib.sha256(text[:-len(suffix)].encode()).hexdigest() == detail["sha256"]
        if not matches:
            raise StoreError("observed request bytes changed")
        if (reply.get("role") != "assistant" or not isinstance(reply.get("id"), str)
                or not reply["id"] or reply["id"].startswith("idx-")
                or not isinstance(reply.get("text"), str) or len(reply["text"].encode()) > 1_000_000):
            raise StoreError("invalid assistant receipt")
        return {"id": reply["id"], "text": reply["text"]}

    reply = observed(first)
    if reply != observed(second):
        raise StoreError("reply changed between observations")
    envelope = json.loads(reply["text"])
    if (not isinstance(envelope, dict) or set(envelope) != {"selection_sha256", "decision"}
            or envelope["selection_sha256"] != context["selection_sha256"]):
        raise StoreError("reply context revision mismatch")
    mission = store.get_mission(mission_id)
    current = verify_sources(Path(mission["workspace"]), context["manifest"])
    if current["selection_sha256"] != context["selection_sha256"]:
        raise StoreError("current context revision mismatch")
    decision = validate_decision(envelope["decision"], expected_mission_id=mission_id,
                                 expected_iteration=mission["iteration"] + 1,
                                 seen_action_ids=store.seen_action_ids(mission_id))
    return {"state": "context_reply_checked", "send_id": request["id"],
            "message_id": reply["id"], "selection_sha256": context["selection_sha256"],
            "reply_sha256": hashlib.sha256(reply["text"].encode()).hexdigest(),
            "decision": decision, "execution_authorized": False, "completion_verified": False,
            "attachment_contents_verified": False, "evidence_source": "host_observation_supplied"}


def finalize_native(store: Store, mission_id: str, first: dict, second: dict,
                    evidence: list[dict], review: dict) -> dict:
    """Persist operator-reviewed completion, not a human approval or release."""
    return store.finalize_native(mission_id, first, second, evidence, review)


def prepare_context_action(store: Store, mission_id: str, first: dict, second: dict) -> dict:
    """Derive one reservation from a checked response; not an execution grant."""
    checked = check_context_reply(store, mission_id, first, second)
    decision = checked["decision"]
    action = decision.get("action")
    if decision["state"] not in {"EXECUTE", "REQUEST_CONTEXT"} or not isinstance(action, dict):
        raise StoreError("decision has no executable action")
    kind = "process" if action["tool"] in {"run_process", "run_tests"} else "host_tool"
    record = store.reserve_native_action(mission_id, decision["actionId"], action["tool"],
                                        action.get("arguments", {}), receipt_kind=kind,
                                        _checked_context=checked)
    return {"state": "prepared", "record_id": record, "receipt_kind": kind,
            "action": action, "execution_authorized": False,
            "requires_approval": decision["requiresApproval"]}


def confirm_rendered(store: Store, mission_id: str, first: dict, second: dict,
                     attachment_counts: dict) -> dict:
    """Opt-in host-rendered receipt, not an attachment-content attestation.

    Only the marker boundary newline and exact known observer summaries may
    differ. Interior payload bytes remain hash-checked. Raw receipt is retained.
    Counts are caller expectations, not proof of file identity or contents.
    """
    if (not isinstance(attachment_counts, dict) or not attachment_counts
            or set(attachment_counts) - {"file", "image"}
            or any(type(v) is not int or not 1 <= v <= 100
                   for v in attachment_counts.values())):
        raise StoreError("invalid expected attachment counts")
    return confirm(store, mission_id, first, second, _attachment_counts=attachment_counts)


def confirm(store: Store, mission_id: str, first: dict, second: dict, *,
            _attachment_counts: dict | None = None) -> dict:
    """Validate supplied successive observations, retaining uncertain attempts."""
    pending = store.unresolved_outbound(mission_id)
    if pending is None:
        raise StoreError("no native send pending")
    detail = json.loads(pending["detail_json"])
    checkpoint = detail.get("checkpoint") or {}
    if checkpoint.get("channel") != "native_host":
        raise StoreError("pending attempt is not native")
    _bound(store, mission_id, checkpoint["conversation_id"])
    suffix = f"\n\n[cortex-transport send_id={pending['id']}]"
    summaries = ""
    if _attachment_counts is not None:
        for kind in ("file", "image"):
            count = _attachment_counts.get(kind)
            if count:
                plural = "s" if count != 1 else ""
                summaries += (f"\n\n[User attached {count} {kind}{plural}; "
                              f"{kind} contents were not included]")

    def payload(text):
        if _attachment_counts is None:
            return text[:-len(suffix)] if text.endswith(suffix) else None
        if not text.endswith(summaries):
            return None
        wire = text[:-len(summaries)]
        if wire.endswith(suffix):
            return wire[:-len(suffix)]
        single_newline_suffix = suffix[1:]
        if wire.endswith(single_newline_suffix):
            return wire[:-len(single_newline_suffix)]
        return None

    def observed(snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("conversation_id") != checkpoint["conversation_id"]:
            raise StoreError("observation conversation mismatch")
        messages = snapshot.get("messages")
        if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
            raise StoreError("invalid observation messages")
        anchors = [i for i, m in enumerate(messages) if m.get("id") == checkpoint["last_message_id"]]
        if len(anchors) != 1:
            raise StoreError("checkpoint anchor not uniquely observed")
        matches = [m for m in messages[anchors[0] + 1:]
                   if m.get("role") == "user" and isinstance(m.get("text"), str)
                   and payload(m["text"]) is not None]
        if len(matches) != 1:
            raise StoreError("native receipt not uniquely observed")
        m = matches[0]
        if not isinstance(m.get("id"), str) or not m["id"] or m["id"].startswith("idx-"):
            raise StoreError("native receipt identity unavailable")
        if hashlib.sha256(payload(m["text"]).encode()).hexdigest() != detail["sha256"]:
            raise StoreError("native receipt payload mismatch")
        return {"id": m["id"], "text": m["text"]}

    receipt = observed(first)
    if receipt != observed(second):
        raise StoreError("native receipt changed between observations")
    result = {"send_id": pending["id"], "sha256": detail["sha256"],
              "message_id": receipt["id"], "evidence_source": "host_observation_supplied",
              "reconciled": True}
    if _attachment_counts is not None:
        result.update({"observation_contract": "host-rendered-attachments.v1",
                       "raw_receipt": receipt,
                       "expected_attachment_counts": dict(_attachment_counts),
                       "attachment_contents_verified": False})
    store.record_transport_event(str(uuid.uuid4()), mission_id, "MESSAGE_DELIVERED", result)
    return result


def main():
    """Bounded JSON stdin; never puts message content in command arguments."""
    import argparse
    import os
    from pathlib import Path
    import sqlite3
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    store = None
    try:
        raw = sys.stdin.buffer.read(2_000_001)
        if len(raw) > 2_000_000:
            raise StoreError("request too large")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise StoreError("request must be an object")
        operation = request.pop("operation")
        allowed = {"prepare": {"mission_id", "conversation_id", "before_message_id", "message"},
                   "prepare_context": {"mission_id", "conversation_id", "before_message_id", "message", "manifest"},
                   "init": {"mission_id", "objective", "workspace", "conversation_id"},
                   "confirm": {"mission_id", "first", "second"},
                   "check_context_reply": {"mission_id", "first", "second"},
                   "prepare_context_action": {"mission_id", "first", "second"},
                   "confirm_rendered": {"mission_id", "first", "second", "attachment_counts"},
                   "status": {"mission_id"},
                   "define_acceptance": {"mission_id", "criteria"},
                   "check_acceptance_evidence": {"mission_id", "evidence"},
                   "finalize_native": {"mission_id", "first", "second", "evidence", "review"},
                   "stop": {"mission_id", "reason"},
                   "attach_handle": {"mission_id", "record_id", "host", "handle"},
                   "action_prepare": {"mission_id", "action_id", "tool", "arguments"},
                   "tool_prepare": {"mission_id", "action_id", "tool", "arguments"},
                   "tool_confirm": {"mission_id", "record_id", "outcome", "tool_result", "verification"},
                   "action_confirm": {"mission_id", "record_id", "exit_code", "evidence"}}
        if operation not in allowed or set(request) != allowed[operation]:
            raise StoreError("invalid request fields")
        if operation == "init":
            if (any(not isinstance(v, str) or not v or len(v) > 8000 for v in request.values())
                    or not Path(request["workspace"]).is_dir()
                    or any(c in request["conversation_id"] for c in "/?#\\\n\r")):
                raise StoreError("invalid native mission initialization")
            # Exclusively reserve a new DB. A partial initialization is retained
            # on failure and never mistaken for permission to overwrite it.
            descriptor = os.open(args.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            store = Store(args.db, recover_interrupted=False)
            store.create_mission(request["mission_id"], request["objective"], request["workspace"])
            store.bind_conversation(str(uuid.uuid4()), request["mission_id"],
                                    "https://chatgpt.com/c/" + request["conversation_id"])
            print(json.dumps({"state": "initialized", "mission_id": request["mission_id"],
                              "release_eligible": False, "executor_verified": False}))
            return 0
        if args.db.is_symlink() or not args.db.is_file():
            raise StoreError("existing authorized database required")
        store = Store(args.db, recover_interrupted=False)
        if operation == "prepare":
            result = prepare(store, **request)
        elif operation == "define_acceptance":
            result = define_acceptance(store, **request)
        elif operation == "check_acceptance_evidence":
            result = check_acceptance_evidence(store, **request)
        elif operation == "finalize_native":
            result = finalize_native(store, **request)
        elif operation == "prepare_context":
            result = prepare_context(store, **request)
        elif operation == "confirm":
            result = confirm(store, **request)
        elif operation == "check_context_reply":
            result = check_context_reply(store, **request)
        elif operation == "prepare_context_action":
            result = prepare_context_action(store, **request)
        elif operation == "confirm_rendered":
            result = confirm_rendered(store, **request)
        elif operation == "stop":
            result = {"state": store.stop_native(**request), "external_processes_stopped": False,
                      "pending": store.unresolved_outbound(request["mission_id"]),
                      "pending_actions": store.pending_native_actions(request["mission_id"])}
        elif operation == "action_prepare":
            result = {"state": "prepared", "record_id": store.reserve_native_action(**request),
                      "execution_authorized": False}
        elif operation == "attach_handle":
            result = store.attach_native_handle(**request)
        elif operation == "action_confirm":
            store.finish_native_action(**request)
            result = {"state": "recorded", "evidence_source": "host_observation_supplied"}
        elif operation == "tool_prepare":
            result = {"state": "prepared", "record_id": store.reserve_native_action(**request, receipt_kind="host_tool"),
                      "execution_authorized": False}
        elif operation == "tool_confirm":
            store.finish_native_tool_action(**request)
            result = {"state": "recorded", "evidence_source": "host_observation_supplied", "exit_code": None}
        else:
            mission = store.get_mission(request["mission_id"])
            result = {"state": mission["state"], "iteration": mission["iteration"],
                      "pending": store.unresolved_outbound(request["mission_id"]),
                      "pending_actions": store.pending_native_actions(request["mission_id"])}
        print(json.dumps(result))
        return 0
    except (StoreError, DecisionError, ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        print(json.dumps({"state": "failed", "reason": "native journal rejected request; do not send or retry"}))
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
