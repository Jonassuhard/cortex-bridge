# v0.5.4 Hybrid Intent Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route one composer safely among exact ChatGPT chat, vault-confined `GeneralMission`, and one server-scoped `LocalAliasAction`, using deterministic rules first and local Ollama only for ambiguity.

**Architecture:** A pure deterministic parser and bounded loopback classifier produce non-authoritative route decisions held in bounded memory; the server freezes `general_mission` versus `local_alias_action` in the route token. General missions alone use vault `WorkspaceHandle`, `MissionLoop`, generic `ToolExecutor`, writers/outboxes and ChatGPT, while a local alias action uses the durable plan's fixed worker and effect gate against one cataloged standard alias with zero mission/browser/chat path. The frontend consumes the prior UI plan's local-action component and keeps routing, clarification, access, finalization and reconciliation state out of ChatGPT history.

**Tech Stack:** Python 3.11/3.14, FastAPI/Pydantic, SQLite, descriptor-relative macOS worker IPC, TypeScript, React 19, Web Workers/Web Crypto, Vitest/Testing Library, Playwright, Chrome MV3 JavaScript/IndexedDB/Web Crypto, Node test runner.

**Spec:** `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md` (approved SHA-256 `472ae88687f6df00be1aac7bb33af536b0456fdc7fd04b7bb5f95e637e4b38f5`) plus normative `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` (approved SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`)

## Global Constraints

- Deterministic high-precision rules run first; local Ollama is called exactly once only for genuinely ambiguous candidates, never for obvious chat, obvious local action, attachment-only input, capture, disabled routing, or `Exécuter…`.
- Ollama is loopback-only, `stream=false`, no tools, temperature zero, 2,048-token context, one active call plus a queue of two, a 2,000 ms warm deadline, no retry, no proxy environment, no automatic model pull/switch/load/unload, and no cloud fallback.
- `/api/intent/route` creates no chat run, mission, upload, writer, outbox, approval, browser command, tool call, SQLite product record, or filesystem mutation; optional named bounded audit is tested separately.
- The four route outcomes are exactly `send_exact_chat`, `open_execution_preflight`, `ask_user`, and `show_local_notice`; a model result never sends, creates authority, grants a capability, approves, or executes.
- Exact chat preserves the original draft bytes at storage, digest, and Cortex-to-extension boundaries; trimming is allowed only to reject an empty draft.
- Classification and clarification stay local to Cortex, never enter the conversation message list, and never reach ChatGPT. Ollama sees only draft, locale, attachment presence, and bounded structured clarification.
- A route is 43-character unpadded base64url, single-use, handle/generation/draft/request-epoch/decision-bound, expires after five minutes, and is limited to 128 global/eight per handle with oldest-unconfirmed eviction.
- A conversation handle is server-minted with 256 bits of entropy, generation-bound, expires after 30 minutes of inactivity, is capped at 256, and is revoked on deletion, generation change, or restart unless durable-result lookup already exists.
- Consume `StorageContract(home).probe() -> StorageStatus`, `.assert_runtime_ready() -> StorageStatus`, `.open() -> StorageBinding`, `.revalidate(binding) -> MountFacts`, and `.open_workspace(binding, requested) -> WorkspaceHandle`; do not modify `console/storage_contract.py` or infer workspace health from a path.
- Consume `WorkspaceHandle.identity`, `.mount_fd`, `.workspace_fd`, `.display_path`, `.revalidate()`, `.duplicate_workspace_fd()`, and `.close()`; `ToolExecutor(workspace: WorkspaceHandle, *, effect_gate: EffectGate, test_commands: list[list[str]] | None = None)` never receives a path string.
- Consume `EffectGate.status/register_pending_approval/decide_approval/activate_mission_effect/begin_direct_intent/activate_direct_intent/begin_local_alias_intent/activate_local_alias_intent/assert_activation/record_blocked_ownership/succeed/fail/outcome_unclear/request_stop/settle_stop/reset_stop/reconcile_startup`; do not modify `console/effect_gate.py` or `orchestration/store.py` in this plan.
- Direct/admin mutation requests carry `effect: {requestId, epoch, operation, payloadDigest}`; server registries choose owner/category. Approval echoes mission/action/epoch/argumentsDigest/nonce/scope/approve. Browser commands require `EffectActivation | ExistingSessionReadPermit | StopCleanupPermit`.
- STOP status is `{schemaVersion:1,state,epoch,acceptingEffects,activeEffectCount,outcomeUnclearCount,resetAllowed,updatedAt}`. The product reset API requires an exact-Origin bounded UI session, a prepared two-minute single-use 256-bit nonce, `resetAttemptId`, `expectedStateVersion`, `expectedAuthorizationEpoch`, and the UI-session header; only its server wrapper calls internal `EffectGate.reset_stop(expected_epoch=...)`. Reset never restores consent or resumes old work.
- `GeneralMission` alone creates a vault-backed grant during finalization and remains confined to verified `20_WORKSPACES`; Desktop, Documents and Downloads are never a `WorkspaceGrant`, `WorkspaceHandle`, mission target or generic executor input.
- `LocalAliasAction` is a distinct durable resource for exactly one `create_directory` leaf below server-owned `desktop|documents|downloads`. It creates no mission, writer, outbox, upload, browser command, extension ledger or generic executor call.
- Startup, routing and finalization never open a protected standard alias. Only a user-clicked access check or an already approved local write may start the fixed durable worker and potentially surface a macOS TCC prompt; Cortex never controls that prompt.
- Local-action finalization and activation each require `StorageContract.assert_runtime_ready()`, current managed-runtime truth, STOP/authorization epoch, a matching unexpired 15-minute access observation and the exact catalog revision.
- Consume `LocalAliasWorkerRequest`, `LocalAliasWorkerReceipt`, `BlockedLocalAliasWorker`, `BlockedWorkerActivationPermit`, `LocalAliasWorkerRunner(effect_gate, installed_home, storage_contract).spawn_blocked/assert_pre_activation_ready/run/abort_blocked`, internal-only `LocalAliasHandle`, and the durable schema-v3 `local_alias_action/filesystem` plus `direct_ui/sensitive_read` registrations; do not modify or recreate their implementation, permit binding/readiness barriers, installer/attestation, effect schema, owned-process runner, reconciliation or `mkdirat` boundary.
- A local leaf is NFC, one non-hidden component, at most 120 UTF-8 bytes, with no slash, NUL, ASCII control, bidi control, leading/trailing whitespace, `.` or `..`; normalization changes require visible confirmation.
- Exact-chat and `GeneralMission` finalization alone create `writer_state=WAITING_FOR_WRITER` and an ineligible outbox. Only their explicit CAS admission allocates one of two global writer slots; capacity release/restart never auto-admits a third resource. `LocalAliasAction` finalization creates neither writer state nor outbox.
- Every outbound message is immutable in a durable outbox before transport. `PREPARING_DISPATCH` is a proven no-effect state; `DISPATCHING` without a signed receipt becomes `DELIVERY_UNCERTAIN` and is never replayed automatically.
- Mutation-capable handles require the fixed extension ID, enrolled Ed25519 identity, signed pairing challenge, matching instance/storage generation, stable HMAC account fingerprint, fresh single-use `classic_chat` `SurfaceProof`, consent version, and authorization epoch.
- The extension's prepare phase performs no DOM mutation; execute consumes the exact proof once. Work/unknown/stale/missing surface or account proof fails before mutation with the spec's distinct code.
- Public documentation remains English; product copy remains the exact French copy from the spec. UI state is text/focus/keyboard accessible and reduced motion changes no information.
- No Chrome, runtime, Ollama, Keychain, storage, upload, filesystem effect, external message, live owner acceptance, merge, tag, push, or release mutation is performed while writing or reviewing this plan.
- Python tests import stdlib `sys` and `unittest` and use no third-party test runner: synchronous cases live in `unittest.TestCase`, async cases in `unittest.IsolatedAsyncioTestCase`, matrices use loops plus `self.subTest`, and every newly created directly executed module loads its suite, rejects `countTestCases() == 0`, runs it with `unittest.TextTestRunner(verbosity=2)`, and exits nonzero unless `wasSuccessful()`.

Every new Python test module invoked as `"$PYTHON" tests/test_name.py` ends with this exact discovery guard, so a module-level function or empty suite cannot produce a false GREEN:

```python
if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() == 0:
        raise SystemExit("ZERO_TESTS_SELECTED")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
```

---

## File Map

- Create `console/intent_models.py`, `console/intent_rules.py`, `console/intent_classifier.py`: strict schemas, pure high-precision rules, bounded loopback classifier.
- Create `console/workspace_catalog.py`, `console/local_alias_actions.py`, `console/intent_routes.py`, `console/intent_store.py`: vault references, fixed local-alias catalog/access/action services, bounded routes and durable intent-specific records in the existing SQLite database.
- Create `console/intent_router.py`: FastAPI route, clarification, finalization, upload, admission, cancel, abandonment, reconciliation, legacy disposition, enrollment, and STOP-reset adapters.
- Modify `console/server.py`, `console/missions.py`, `console/chat.py`, `console/attachments.py`, `console/chrome_extension.py`, `console/settings.py`, `console/onboarding.py`: integrate without reviving legacy task mutation or bypassing shared authority.
- Modify general-mission orchestration adapters only where needed to consume the frozen execution class; do not add any local alias handle or operation to `ToolExecutor`, `MissionLoop`, process, browser or generic tool registries.
- Modify `chrome-extension/manifest.json`, `chrome-extension/protocol.js`, `chrome-extension/service-worker.js`, `chrome-extension/service-worker-core.js`, `chrome-extension/chatgpt-content.js`, `chrome-extension/cortex-content.js`: pinned identity, enrollment, pairing, surface proofs, dispatch ledger, and prepare/execute.
- Create `frontend/lib/intent.ts`, `frontend/hooks/useIntentRouter.ts`, `frontend/workers/attachmentDigest.worker.ts`, clarification/general-mission/notice components, and wire the prior UI plan's `LocalAliasActionPanel`; modify composer/app/workspace/settings/pipeline UI to consume them.
- Create focused Python, extension, frontend, and Playwright test files named in the tasks below; update packaging, docs, aggregate gates, and the v0.5.0 supersession note.

### Task 1: Define strict intent schemas and deterministic rules

**Files:**
- Create: `console/intent_models.py`
- Create: `console/intent_rules.py`
- Create: `tests/test_intent_rules.py`
- Create: `tests/test_intent_models.py`

**Interfaces:**
- Consumes: raw UTF-8 draft, locale `fr | en`, validated attachment descriptor metadata.
- Produces: strict `ExecutionClass`, `ExecutionIntent`, `VaultWorkspaceRef`, `LocalAliasRef`, `OperationScope`, `AttachmentDescriptor`, `RouteRequest`, `ClarificationRequest`, `RuleDecision`, and `validate_local_leaf(raw: str) -> LocalLeafValidation`; `route_by_rules(draft: str, locale: Literal["fr", "en"]) -> RuleDecision | None`.

- [ ] **Step 1: Write the failing table-driven corpus and schema boundaries**

```python
class IntentRulesTest(unittest.TestCase):
    def test_high_precision_rules(self):
        cases = [
            ("Quelle est la capitale du Japon ?", "send_exact_chat"),
            ("Explique-moi comment créer un dossier sur macOS.", "send_exact_chat"),
            ("Donne-moi un exemple de commande mkdir sans l'exécuter.", "send_exact_chat"),
            ("cree moi un dossier cortex-live-test sur mon bureau", "open_execution_preflight"),
            ("Peux-tu créer le dossier Sample dans Documents ?", "open_execution_preflight"),
            ('Il a dit "crée un dossier test"', "send_exact_chat"),
            ("Ne l'envoie pas à ChatGPT, crée le dossier", "ask_user"),
        ]
        for draft, action in cases:
            with self.subTest(draft=draft):
                self.assertEqual(route_by_rules(draft, "fr").action, action)

    def test_obvious_desktop_folder_is_local_alias_not_general_mission(self):
        decision = route_by_rules("cree moi un dossier cortex-live-test sur mon bureau", "fr")
        self.assertEqual(decision.execution_class, "local_alias_action")
        self.assertEqual(decision.intent.target, "desktop")
        self.assertEqual(decision.intent.artifact_name, "cortex-live-test")

    def test_general_mission_can_only_reference_vault_workspace(self):
        decision = route_by_rules("Dans mon espace de travail, prépare le projet Atlas", "fr")
        self.assertEqual(decision.execution_class, "general_mission")
        self.assertEqual(decision.intent.target, "default_workspace")

    def test_artifact_name_must_be_an_exact_contiguous_span(self):
        with self.assertRaisesRegex(IntentValidationError, "ARTIFACT_SPAN_MISMATCH"):
            ExecutionIntent.from_candidate(DRAFT, artifact_name="sample")
```

Cover accent, case, punctuation, whitespace, fully negated, hypothetical, tutorial, quoted, destructive/network/unsupported operations, control characters, slash/backslash, `.`/`..`, leading dot, leading/trailing whitespace, bidi controls, code fence, shell syntax, 1/120/121 UTF-8-byte leaves, NFC-preserving and NFC-changing input, 8,000-character draft, 32 KiB body, and all descriptor bounds. Arbitrary paths, home/root, nested names and additional project aliases must return clarification/local notice, never `local_alias_action` or silent `general_mission` fallback.

- [ ] **Step 2: Run focused tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_rules.py
"$PYTHON" tests/test_intent_models.py
```
Expected: `FAIL` because the schema and rule modules do not exist.

- [ ] **Step 3: Implement strict models and pure rules**

```python
ExecutionClass = Literal["general_mission", "local_alias_action"]
LocalAlias = Literal["desktop", "documents", "downloads"]

@dataclass(frozen=True, slots=True)
class VaultWorkspaceRef:
    kind: Literal["vault"]
    catalog_entry_id: str
    revision: int
    storage_transaction_id: str
    root: Literal["20_WORKSPACES"]

@dataclass(frozen=True, slots=True)
class LocalAliasRef:
    kind: Literal["local_alias"]
    alias: LocalAlias
    catalog_entry_id: str
    revision: int

WorkspaceRef = VaultWorkspaceRef | LocalAliasRef

class ExecutionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intent: Literal["chat", "local_change", "unclear", "unsupported"]
    confidence: Literal["high", "medium", "low"]
    operation: Literal["create_directory", "other", "unsupported"]
    artifact_name: str | None
    target: Literal["desktop", "documents", "downloads", "default_workspace", "unspecified"]
    missing: tuple[Literal["target", "artifact_name"], ...]

@dataclass(frozen=True, slots=True)
class LocalLeafValidation:
    normalized_leaf: str
    confirmation_required: bool

@dataclass(frozen=True, slots=True)
class RuleDecision:
    action: Literal["send_exact_chat", "open_execution_preflight", "ask_user", "show_local_notice"]
    intent: ExecutionIntent | None
    execution_class: ExecutionClass | None
    reason_code: str

def validate_local_leaf(raw: str) -> LocalLeafValidation: ...
```

Use ordered token tables for French/English actions, local objects/targets, explanatory exclusions, negation, and unsupported categories. The server rule selects `local_alias_action` only for exact `create_directory` plus one fixed standard alias/valid leaf; `default_workspace` and agentic/multi-step work select `general_mission`. Preserve the exact artifact substring and return ambiguity instead of manufacturing a path, permission, class, alias or name. Ollama may later recommend `ask_user` but cannot mint either `WorkspaceRef` or change the server-selected execution class.

- [ ] **Step 4: Re-run focused tests to prove GREEN**

Run the two commands from Step 2.
Expected: every corpus and boundary case `PASS`; no rule imports FastAPI, filesystem, transport, mission, or Ollama code.

- [ ] **Step 5: Commit the pure boundary**

```bash
git add console/intent_models.py console/intent_rules.py tests/test_intent_rules.py tests/test_intent_models.py
git commit -m "feat: add strict deterministic intent rules"
```

### Task 2: Add the bounded local Ollama classifier and truthful prewarm controls

**Files:**
- Create: `console/intent_classifier.py`
- Modify: `console/settings.py:64-106,184-215`
- Modify: `console/onboarding.py:278-365`
- Create: `tests/test_intent_classifier.py`
- Modify: `tests/test_chat_settings_api.py`

**Interfaces:**
- Consumes: Task 1 ambiguity metadata but no `WorkspaceRef`, catalog ID/revision or authority-bearing execution class; settings `intent_router_model`, `intent_router_prewarm`, `intent_routing_enabled`.
- Produces: `OllamaIntentClassifier.classify(request: ClassifierInput) -> ClassificationResult`; non-authorizing `ClassifierSuggestion`; `IntentCircuitBreaker`; `PrewarmLease.stop_renewals() -> None` that never unloads a model.

- [ ] **Step 1: Write failing classifier deadline and privacy tests**

```python
class IntentClassifierTest(unittest.IsolatedAsyncioTestCase):
    async def test_model_not_loaded_returns_under_250ms_without_chat_call(self):
        self.fake_ollama.tags = ["qwen3.5:9b"]
        self.fake_ollama.ps = []
        result = await self.classifier.classify(candidate("Range tout ça proprement"))
        self.assertEqual(result.degraded_reason, "model_not_loaded")
        self.assertLess(result.latency_ms, 250)
        self.assertEqual(self.fake_ollama.chat_calls, [])

    async def test_timeout_keeps_slot_until_worker_ends_and_opens_breaker(self):
        self.fake_ollama.keep_working_after_disconnect = True
        first = await self.classifier.classify(AMBIGUOUS)
        second = await self.classifier.classify(AMBIGUOUS)
        self.assertEqual(first.degraded_reason, "cold_race")
        self.assertEqual(second.degraded_reason, "busy")
        self.assertEqual(self.fake_ollama.chat_call_count, 1)
```

Assert one active/two queued, fourth immediate `busy`, exact 2,000 ms deadline, 30-second breaker, single half-open probe, invalid/extra/contradictory JSON fallback, oversized serialized request, proxy env ignored, no tool field, no filename descriptor/history/title/URL/path/account in request, and `model_used=null` unless a valid accepted response exists.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_classifier.py
"$PYTHON" tests/test_chat_settings_api.py
```
Expected: `FAIL` because the bounded classifier and intent settings do not exist.

- [ ] **Step 3: Implement the loopback-only classifier**

```python
@dataclass(frozen=True, slots=True)
class ClassifierSuggestion:
    intent: Literal["chat", "local_change", "unclear", "unsupported"]
    confidence: Literal["high", "medium", "low"]
    missing: tuple[Literal["target", "artifact_name", "operation"], ...]
    clarification: ClarificationQuestion | None

@dataclass(frozen=True, slots=True)
class ClassificationResult:
    suggestion: ClassifierSuggestion | None
    model_attempted: bool
    model_used: str | None
    observed_digest: str | None
    decision_accepted: bool
    degraded_reason: DegradedReason
    latency_ms: int

class OllamaIntentClassifier:
    async def classify(self, request: ClassifierInput) -> ClassificationResult: ...
```

Probe `/api/tags` and `/api/ps` without proxy inheritance. Call loopback `/api/chat` once only if already loaded, with the exact JSON schema and bounded output. The schema has no execution-class, alias, path, leaf, catalog, grant or capability field. The server may use the suggestion only to choose a local clarification/notice or exact-chat candidate, then reruns deterministic validation; it alone freezes `general_mission|local_alias_action` and resolves a catalog entry. Prewarm begins only after explicit opt-in and app readiness; stopping cancels only Cortex keepalive renewals.

- [ ] **Step 4: Re-run focused tests to prove GREEN**

Run the two commands from Step 2.
Expected: all tests `PASS`; no cold composer load, retry, unload, cloud call, or executor `_chat_sync()` reuse occurs.

- [ ] **Step 5: Commit classifier and settings**

```bash
git add console/intent_classifier.py console/settings.py console/onboarding.py tests/test_intent_classifier.py tests/test_chat_settings_api.py
git commit -m "feat: classify ambiguous intent locally"
```

### Task 3: Partition vault workspaces from fixed local aliases and verify access only on explicit action

**Files:**
- Create: `console/workspace_catalog.py`
- Create: `console/local_alias_actions.py`
- Create: `tests/test_workspace_catalog.py`
- Create: `tests/test_local_alias_access.py`
- Inspect for conformance only: `console/storage_contract.py`, `executor/workspace_handle.py`, `executor/local_alias_worker.py`, `executor/local_alias_worker_runner.py`
- Run without modification: `tests/test_workspace_path_fuzzing.py`, `tests/test_local_alias_worker.py`, `tests/test_local_alias_worker_runner.py`

**Interfaces:**
- Consumes unchanged: `StorageContract.assert_runtime_ready() -> StorageStatus`; vault-only `StorageContract.open()/open_workspace()` and `WorkspaceHandle`; durable `LocalAliasCatalogEntry`, `LocalAliasAccessObservation`, `LocalAliasGrant`, `DirectEffectRequest`, `EffectGate.begin_direct_intent/succeed/fail`, `EffectGate.activate_direct_intent(effect_id: str, *, blocked_worker_permit: BlockedWorkerActivationPermit | None = None) -> EffectActivation` with the permit mandatory for exactly `direct_ui/sensitive_read/verify_local_alias_access`, `LocalAliasWorkerRequest`, `LocalAliasWorkerReceipt`, and exact `LocalAliasWorkerRunner(effect_gate: EffectGate, installed_home: Path, storage_contract: StorageContract)`, `.spawn_blocked`, `.assert_pre_activation_ready(*, intent: EffectIntent) -> BlockedWorkerActivationPermit`, `.run`, `.abort_blocked` ordering.
- Produces: `VaultWorkspaceCatalog.validate_entry(id, revision) -> VaultWorkspaceRef`; fixed `LocalAliasCatalog.entries() -> tuple[LocalAliasCatalogEntry, ...]`; `LocalAliasAccessService.prepare(alias, *, ui_session, origin) -> LocalAliasAccessChallenge`; `await LocalAliasAccessService.verify(challenge, *, ui_session, origin) -> LocalAliasAccessObservation`. It creates no `LocalAliasGrant` or action here.

- [ ] **Step 1: Write failing authority-partition and explicit access-check tests**

```python
class WorkspaceCatalogTest(unittest.TestCase):
    def test_catalog_startup_records_fixed_aliases_without_opening_them(self):
        self.assertEqual([(row.alias, row.label) for row in self.catalog.entries()], [
            ("desktop", "Bureau"),
            ("documents", "Documents"),
            ("downloads", "Téléchargements"),
        ])
        self.assertEqual(self.open_spy.calls, [])

    def test_desktop_can_never_materialize_a_workspace_handle(self):
        with self.assertRaisesRegex(AuthorityError, "LOCAL_ALIAS_NOT_VAULT_WORKSPACE"):
            self.vault_catalog.validate_entry(local_alias_entry_id("desktop"), revision=7)

class LocalAliasAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_access_worker_starts_only_after_explicit_prepared_action(self):
        challenge = self.access_service.prepare("desktop", ui_session=SESSION, origin=ORIGIN)
        self.assertEqual(protected_alias_open_count(), 0)
        observation = await self.access_service.verify(
            challenge, ui_session=SESSION, origin=ORIGIN,
        )
        self.assertEqual(observation.alias, "desktop")
        self.assertAlmostEqual(observation.expires_at, observation.verified_at + 900, places=6)
        self.assertEqual(worker_requests(), [LocalAliasWorkerRequest(
            operation="verify_access", alias="desktop", allowed_leaf=None,
            catalog_entry_id=challenge.catalog_entry_id,
            catalog_revision=challenge.catalog_revision, expected_identity=None,
        )])
        self.assertEqual(self.trace, [
            "readiness-prepare", "intent-fsynced", "runner-spawn-readiness", "spawned-blocked",
            "ownership-fsynced", "runner-pre-activation-ready", "permit-issued",
            "activation-received-permit", "effect-active",
            "runner-pre-release-ready", "released", "receipt-fsynced",
            "child-closed-reaped",
        ])
        self.assertEqual(self.runner.readiness_barrier_count, 3)
        permit = self.runner.issued_permits[0]
        self.assertIs(
            self.effect_gate.direct_activation_calls[0].blocked_worker_permit,
            permit,
        )
        self.assertEqual(
            self.runner.binding_for(permit),
            (intent_effect_id(), owned_process_identity(), STORAGE_TRANSACTION_ID, STOP_EPOCH),
        )

    async def test_readiness_loss_at_each_gate_never_releases_access_worker(self):
        phases = {"spawn": 1, "before_activation": 2, "before_release": 3}
        for loss in ("detach", "transition", "rollback", "lease"):
            for phase, expected_calls in phases.items():
                with self.subTest(loss=loss, phase=phase):
                    self.reset_access_fixture(readiness_loss=loss, failure_phase=phase)
                    challenge = self.access_service.prepare(
                        "desktop", ui_session=SESSION, origin=ORIGIN,
                    )
                    with self.assertRaisesRegex(LocalAliasAccessError, "STORAGE_NOT_READY"):
                        await self.access_service.verify(
                            challenge, ui_session=SESSION, origin=ORIGIN,
                        )
                    self.assertEqual(self.runner.readiness_barrier_count, expected_calls)
                    self.assertEqual(self.runner.release_count, 0)
                    self.assertEqual(self.repository.observation_count, 0)
                    self.assertEqual(self.worker.mutation_count, 0)
                    if phase == "spawn":
                        self.assertEqual(self.runner.spawn_calls, [])
                        self.assertEqual(self.effect_gate.direct_activation_calls, [])
                    elif phase == "before_activation":
                        self.assertTrue(self.runner.abort_awaited)
                        self.assertEqual(self.effect_gate.direct_activation_calls, [])
                    else:
                        self.assertTrue(self.runner.run_cleanup_awaited)
                        self.assertIsNotNone(
                            self.effect_gate.direct_activation_calls[0].blocked_worker_permit,
                        )
                        self.assertEqual(self.effect_gate.effect_state(), "failed")
                        self.assertEqual(self.effect_gate.terminal_code(), "STORAGE_NOT_READY")
                    self.assertTrue(self.runner.child_closed_and_reaped)
```

Cover fixed alias order/labels/leaves, opaque IDs and monotonic revisions; vault root/descendants only for `VaultWorkspaceRef`; hostile `$HOME` ignored; no alias open at startup/routing/preparation; exact Origin/UI session/envelope; two-minute single-use prepared challenge, cap eight/session and 128 global; healthy runtime/readiness; STOP/consent/epoch/restart invalidation; 60-second timeout, EOF, malformed receipt, cancellation, worker crash and fake TCC hold; `EPERM|EACCES`, unavailable/symlinked/wrong-owner/wrong-type/protected/root/home/CORTEX_HOME/vault/profile/credential/device roots; one 15-minute observation only on exact terminal success. Every failed/unclear check closes worker/FDs, persists a terminal failed sensitive-read effect, creates no observation/grant and leaves STOP reset available.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_workspace_catalog.py
"$PYTHON" tests/test_local_alias_access.py
```
Expected: `FAIL`; the partitioned catalogs and intent-owned access-observation service do not exist.

- [ ] **Step 3: Implement non-authorizing catalogs and bounded access service**

```python
@dataclass(frozen=True, slots=True)
class LocalAliasAccessChallenge:
    verification_id: str
    alias: LocalAlias
    catalog_entry_id: str
    catalog_revision: int
    warning: str
    effect: DirectEffectRequest
    expires_at: float

class LocalAliasRepository(Protocol):
    def record_local_alias_access(self, command: RecordLocalAliasAccess
                                  ) -> LocalAliasAccessObservation: ...
    def current_local_alias_access(self, catalog_entry_id: str, revision: int,
                                   authorization_epoch: int, now: float
                                   ) -> LocalAliasAccessObservation | None: ...

class LocalAliasAccessService:
    def __init__(self, *, repository: LocalAliasRepository,
                 effect_gate: EffectGate,
                 runner: LocalAliasWorkerRunner,
                 storage_contract: StorageContract) -> None: ...
    def prepare(self, alias: LocalAlias, *, ui_session: str,
                origin: ExactFrontendOrigin) -> LocalAliasAccessChallenge: ...
    async def verify(self, challenge: LocalAliasAccessChallenge, *,
                     ui_session: str, origin: ExactFrontendOrigin
                     ) -> LocalAliasAccessObservation: ...
```

Provision only the three fixed definitions from `getuid()`/`getpwuid_r()` metadata without opening their leaves; `$HOME`, client JSON, draft and model output cannot alter them. The service is complete against the injected repository protocol; Task 6 supplies the production SQLite implementation, while Task 3 tests use a recording fake. `prepare` calls readiness but performs no alias open or product-row write and mints the exact `verify_local_alias_access` envelope in bounded memory. `verify` requires byte-identical challenge/session/origin, persists/fsyncs the `direct_ui/sensitive_read` intent, then invokes `spawn_blocked(request=request, intent=intent)`; `LocalAliasWorkerRunner.spawn_blocked()` is the sole owner of the pre-spawn `StorageContract.assert_runtime_ready()` barrier and spawns no child on failure. After blocked ownership is durable the service obtains `permit = runner.assert_pre_activation_ready(intent=intent)` inside the serialized effect transaction; the durable runner binds that unforgeable permit to the exact effect ID, owned PID/PGID/start identity, storage transaction/readiness observation and authorization/STOP epoch. The service must pass that same object to `activate_direct_intent(intent.effect_id, blocked_worker_permit=permit)`; this registered local access operation has no permit-free activation path. `runner.run(...)` owns the third readiness barrier immediately before child release. Detach, transition, rollback, contradictory status or managed-start lease loss before activation returns `STORAGE_NOT_READY`, releases no child and creates no observation. A post-activation/pre-release readiness failure terminalizes the direct effect as `failed/STORAGE_NOT_READY`, creates no observation, closes/reaps the worker and performs zero mutation. A `finally` executes `await runner.abort_blocked(intent=intent, code=terminal_code)` whenever `run` did not take ownership, then verifies the exact PID/PGID/start identity is closed and reaped before returning. Persist the observation only from a valid terminal receipt after the runner has closed/reaped the child. It never calls a shell, generic executor, mission, browser or extension path and never interacts with TCC UI.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the two commands from Step 2, then `"$PYTHON" tests/test_workspace_path_fuzzing.py`, `"$PYTHON" tests/test_local_alias_worker.py`, and `"$PYTHON" tests/test_local_alias_worker_runner.py` as unchanged conformance.
Expected: all tests `PASS`; vault/general-mission and local-alias authority are disjoint, and only the explicit access action can produce one current observation.

- [ ] **Step 5: Commit catalog and global policy correction**

```bash
git add console/workspace_catalog.py console/local_alias_actions.py tests/test_workspace_catalog.py tests/test_local_alias_access.py
git commit -m "feat: partition vault workspaces and local alias access"
```

### Task 4: Manage conversation handles, provisional conversations, routes, and clarification in bounded memory

**Files:**
- Create: `console/intent_routes.py`
- Create: `tests/test_intent_routes.py`
- Modify: `console/missions.py:807-880`

**Interfaces:**
- Consumes: verified extension/account/surface identity from Task 8 and Task 1/2 decisions.
- Produces: `VerifiedConversationBinding(extension_id, enrollment_fingerprint, instance_id, storage_generation, pairing_session_id, surface, account_fingerprint, canonical_key, generation)`; `RouteRecord` with frozen execution class and server-resolved `WorkspaceRef`; `ConversationHandleRegistry.issue(binding)`, `.resolve(token)`, `.revoke_generation(generation)`; `RouteRegistry.create(record)`, `.consume(route_id, handle, decision_digest)`, `.clarify(route_id, answer)`; `POST /api/conversations/provisional` server data.

- [ ] **Step 1: Write failing entropy, capacity, isolation, and clarification tests**

```python
class IntentRouteRegistryTest(unittest.TestCase):
    def test_handle_and_route_tokens_are_43_char_base64url_and_conversation_bound(self):
        handle = self.registries.handles.issue(verified_binding("conv-a"))
        route = self.registries.routes.create(handle, decision(), request_epoch=42)
        self.assertRegex(handle.token, r"^[A-Za-z0-9_-]{43}$")
        self.assertRegex(route.route_id, r"^[A-Za-z0-9_-]{43}$")
        with self.assertRaisesRegex(RouteConflict, "ROUTE_CONVERSATION_MISMATCH"):
            self.registries.routes.consume(route.route_id, other_handle())

    def test_clarification_consumes_old_route_and_allows_two_resolutions_only(self):
        first = self.registries.routes.create_missing_target(
            handle=verified_handle("conv-a"), original_draft="Crée un dossier",
            request_epoch=7, missing_field="target",
        )
        second = self.registries.routes.clarify(first.route_id, target_answer("desktop"))
        with self.assertRaises(RouteExpired):
            self.registries.routes.clarify(first.route_id, target_answer("documents"))
        self.assertNotEqual(second.route_id, first.route_id)
```

Cover 256 handles, 128 global routes, eight per handle, five-minute route TTL, 30-minute handle idle TTL, oldest-unconfirmed eviction only, successor route IDs, service restart invalidation, draft edit/conversation switch/cancel epoch invalidation, structured enum/name/free-text bounds, one visible question, and two resolutions before manual choice.

- [ ] **Step 2: Run tests to prove RED**

Run: `"$PYTHON" tests/test_intent_routes.py`
Expected: `FAIL` because bounded handle/route registries and server provisional identities do not exist.

- [ ] **Step 3: Implement bounded registries and provisional identities**

```python
class RouteRegistry:
    def create(self, *, handle: ConversationHandle, request_epoch: int,
               original_draft: str, decision: RouteDecision) -> RouteRecord: ...
    def clarify(self, route_id: str, answer: ClarificationAnswer) -> RouteRecord: ...
    def consume(self, route_id: str, *, handle: ConversationHandle,
                decision_digest: str) -> RouteRecord: ...

@dataclass(frozen=True, slots=True)
class RouteRecord:
    route_id: str
    conversation_handle: str
    request_epoch: int
    original_draft: str
    decision_digest: str
    action: Literal["send_exact_chat", "open_execution_preflight", "ask_user", "show_local_notice"]
    execution_class: ExecutionClass | None
    workspace_ref: WorkspaceRef | None
    operation: Literal["create_directory"] | None
    normalized_leaf: str | None
```

The route service, not pure rules/classifier/client, resolves the fixed catalog entry and constructs `VaultWorkspaceRef` or `LocalAliasRef` before `RouteRegistry.create`. Clarification creates a successor record and never changes a frozen execution class in place. `POST /api/conversations/provisional` allocates a unique provisional key/generation/handle without opening a tab. On restart an unfinished provisional handle is invalid; the browser draft remains client-side and must obtain a fresh handle. Route records retain original draft in bounded memory only and use keyed HMACs for diagnostics/digests.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run: `"$PYTHON" tests/test_intent_routes.py`
Expected: all tests `PASS`; expired/evicted/consumed/post-restart routes return `ROUTE_EXPIRED` with zero side effects.

- [ ] **Step 5: Commit route state**

```bash
git add console/intent_routes.py console/missions.py tests/test_intent_routes.py
git commit -m "feat: bind intent routes to server conversation handles"
```

### Task 5: Expose the side-effect-free route and explicit local-alias access endpoints

**Files:**
- Create: `console/intent_router.py`
- Modify: `console/server.py:35-90`
- Modify: `pyproject.toml:20-43`
- Create: `tests/test_intent_router_api.py`
- Create: `tests/test_intent_non_mutation.py`
- Modify: `tests/test_local_alias_access.py`
- Modify: `tests/test_server_umask.py`

**Interfaces:**
- Consumes: Tasks 1-4 rules/classifier/catalog/access/registries, UI-session/exact-Origin boundary, and prior UI-plan `LocalActionRuntimeTruth` projection.
- Produces: side-effect-free `POST /api/intent/route`; explicit `POST /api/local-aliases/{alias}/verify-access/prepare` and `POST /api/local-aliases/{alias}/verify-access`; strict discriminated `RouteResponse`; immutable `GeneralMissionPreflight | LocalAliasPreflight`; `decision_digest`; and safe fallback.

- [ ] **Step 1: Write failing API and non-mutation snapshots**

```python
class IntentRouterApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_obvious_folder_request_returns_preflight_without_ollama_or_effect(self):
        before = self.frozen_world.snapshot()
        response = await self.client.post("/api/intent/route", json=folder_request())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["action"], "open_execution_preflight")
        self.assertEqual(body["source"], "rules")
        self.assertIsNone(body["model_used"])
        self.assertEqual(body["executionClass"], "local_alias_action")
        self.assertEqual(body["alias"], "desktop")
        self.assertEqual(body["leaf"], "cortex-live-test")
        self.assertEqual(body["accessState"], "verification_required")
        self.assertIsNone(body["accessObservationId"])
        self.assertEqual(body["requires"], {
            "writeApproval": True, "chatgpt": False, "writer": False,
            "read": False, "process": False, "network": False, "deletion": False,
        })
        self.assertNotIn("missionId", body)
        self.assertEqual(self.frozen_world.snapshot(), before)

    async def test_ambiguous_ollama_chat_stays_local(self):
        self.fake_classifier.result = ollama_chat_high()
        body = (await self.client.post(
            "/api/intent/route", json=ambiguous_request(),
        )).json()
        self.assertEqual(body["action"], "ask_user")
        self.assertEqual(self.transport.commands, [])
        self.assertEqual(self.missions.created, [])
        self.assertEqual(self.chat.runs, [])

    async def test_access_prepare_is_read_only_and_execute_requires_exact_echo(self):
        prepared = await self.client.post(
        "/api/local-aliases/desktop/verify-access/prepare",
        headers=ui_headers(ORIGIN, SESSION),
        )
        self.assertEqual(protected_alias_open_count(), 0)
        body = prepared.json()
        verified = await self.client.post(
            "/api/local-aliases/desktop/verify-access",
            headers=ui_headers(ORIGIN, SESSION), json={
                "verificationId": body["verificationId"], "effect": body["effect"],
            },
        )
        self.assertEqual(verified.json()["alias"], "desktop")
```

Assert strict extra-field rejection, 32 KiB pre-parse rejection, exact response unions and camelCase conversion, attachment descriptor never sent to classifier, text+file local candidate notice, all degraded reasons, local one-question response, exact-chat automatic-finalization instruction, no raw draft/clarification logs, and separately named audit-journal exception. Route/finalization probes for local aliases remain zero. Access prepare requires healthy runtime but opens nothing; execute rejects wrong alias/session/origin/verification ID/request ID/epoch/operation/digest and never accepts client owner/category.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_router_api.py
"$PYTHON" tests/test_intent_non_mutation.py
"$PYTHON" tests/test_local_alias_access.py
```
Expected: `FAIL` because the router module/endpoint is absent.

- [ ] **Step 3: Implement route-only orchestration**

```python
intent_router = APIRouter(prefix="/api/intent")
local_alias_router = APIRouter(prefix="/api/local-aliases")
ExactFrontendOrigin = Annotated[str, Depends(require_exact_frontend_origin)]
UiSessionHeader = Annotated[str, Header(alias="X-Cortex-UI-Session")]

class EffectEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel,
                              populate_by_name=True)
    request_id: UUID
    epoch: int = Field(ge=0)
    operation: str
    payload_digest: Digest

class VerifyLocalAliasAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel,
                              populate_by_name=True)
    verification_id: str
    effect: EffectEnvelope

@intent_router.post("/route", response_model=RouteResponse, response_model_exclude_none=True)
async def route_intent(request: Request) -> RouteResponse:
    body = await strict_json(request, maximum_bytes=32 * 1024)
    parsed = parse_route_or_clarification(body)
    return await intent_service.route(parsed)

@local_alias_router.post("/{alias}/verify-access/prepare")
async def prepare_local_alias_access(
    alias: LocalAlias, origin: ExactFrontendOrigin,
    ui_session: UiSessionHeader,
) -> LocalAliasAccessChallenge: ...

@local_alias_router.post("/{alias}/verify-access")
async def verify_local_alias_access(
    alias: LocalAlias, body: VerifyLocalAliasAccessRequest,
    origin: ExactFrontendOrigin, ui_session: UiSessionHeader,
) -> LocalAliasAccessObservation: ...
```

Create the route before returning every terminal outcome. A `general_mission` route builds mission objective, vault reference, capabilities, operation scope, preallocated mission ID and immutable cloud bytes. A `local_alias_action` route builds only the fixed alias/label/leaf/catalog revision/access state and all-false chat/writer/read/process/network/deletion flags; it has no mission ID, workspace handle, executor/model, writer or cloud payload. `VerifyLocalAliasAccessRequest` contains exactly `{verificationId,effect}` and delegates to Task 3; only this explicit endpoint may release the access worker.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2.
Expected: all tests `PASS`; `/route` alone leaves every persistent/effect surface byte-identical, prepare opens no alias, and access execute creates only its exact sensitive-read effect/observation.

- [ ] **Step 5: Commit the route API**

```bash
git add console/intent_router.py console/server.py pyproject.toml tests/test_intent_router_api.py tests/test_intent_non_mutation.py tests/test_local_alias_access.py tests/test_server_umask.py
git commit -m "feat: expose side effect free intent routing"
```

### Task 6: Add intent-specific durable schema, idempotency, outbox, writer, upload, and migration records

**Files:**
- Create: `console/intent_store.py`
- Modify: `console/server.py`
- Create: `tests/test_intent_store.py`
- Create: `tests/test_local_alias_store.py`
- Run without modification: `tests/test_store_lifecycle.py`, `tests/test_protocol_state_store.py`

**Interfaces:**
- Consumes: existing Cortex SQLite path; durable `SCHEMA_VERSION = 3`, effects plus `local_alias_catalog`, `local_alias_access_observations`, `local_alias_grants`, `local_alias_actions` tables/checks; `EffectGate` owns their migration, effect transitions and startup effect reconciliation. This task adds no DDL for those five durable concerns.
- Produces: `IntentStore.migrate()`, `transaction_immediate()`, final-action/chat-v2/general-mission-contract/upload/outbox/writer/dispatch/enrollment/legacy APIs and startup ordering, plus typed `LocalAliasRepository` row operations over the pre-existing v3 tables.

- [ ] **Step 1: Write failing transaction and recovery tests**

```python
class IntentStoreTest(unittest.TestCase):
    def test_no_file_chat_finalization_is_one_atomic_waiting_resource(self):
        result = self.intent_store.create_chat_final_action(command())
        self.assertEqual(self.intent_store.count("final_actions"), 1)
        self.assertEqual(self.intent_store.count("chat_runs_v2"), 1)
        self.assertEqual(self.intent_store.count("message_outbox"), 1)
        self.assertEqual(result.writer_state, "WAITING_FOR_WRITER")
        self.assertFalse(result.outbox_eligible)
        self.assertEqual(self.intent_store.count("conversation_writer_leases"), 0)

    def test_same_idempotency_key_changed_digest_conflicts_before_effect(self):
        self.intent_store.create_chat_final_action(command(key=KEY, digest="a" * 64))
        with self.assertRaisesRegex(IntentConflict, "IDEMPOTENCY_CONFLICT"):
            self.intent_store.create_chat_final_action(command(key=KEY, digest="b" * 64))

    def test_local_alias_rows_use_durable_v3_schema_without_mission_or_writer(self):
        action = self.intent_store.finalize_local_alias_action(local_alias_command())
        self.assertEqual(action.state, "awaiting_approval")
        self.assertEqual(self.intent_store.count("local_alias_grants"), 1)
        self.assertEqual(self.intent_store.count("local_alias_actions"), 1)
        self.assertEqual(self.intent_store.count("missions"), 0)
        self.assertEqual(self.intent_store.count("conversation_writer_leases"), 0)
        self.assertEqual(self.intent_store.schema_version, 3)
```

Add failpoints before/after each atomic boundary in the spec table; uniqueness for route digest, idempotency key, resource/sequence, active destination writer; 15/30-minute and two-hour expiries; 24-hour/30-day/10,000-record retention; key ID rotation; `DISPATCHING` recovery to uncertainty; crossed preparation/outbox pairs; and startup order migration → legacy import → final-action/outbox → upload → orphan collection.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_store.py
"$PYTHON" tests/test_local_alias_store.py
```
Expected: `FAIL` because the intent-owned store/repository and typed local-alias row operations do not exist; the durable schema-v3 migration is a green prerequisite.

- [ ] **Step 3: Implement versioned migrations and typed transactions**

```python
class IntentStore:
    def ensure_local_alias_catalog(self, entries: tuple[LocalAliasCatalogEntry, ...]
                                   ) -> tuple[LocalAliasCatalogEntry, ...]: ...
    def create_chat_final_action(self, command: CreateChatFinalAction) -> FinalActionReceipt: ...
    def create_mission_final_action(self, command: CreateMissionFinalAction) -> FinalActionReceipt: ...
    def admit_writer(self, final_action_id: str, expected_version: int) -> WriterAdmissionReceipt: ...
    def prepare_dispatch(self, message_id: str, fences: DispatchFences) -> DispatchPreparation: ...
    def commit_dispatch_boundary(self, command: CommitDispatchBoundary) -> DispatchingReceipt: ...
    def record_local_alias_access(self, command: RecordLocalAliasAccess) -> LocalAliasAccessObservation: ...
    def current_local_alias_access(self, catalog_entry_id: str, revision: int,
                                   authorization_epoch: int, now: float
                                   ) -> LocalAliasAccessObservation | None: ...
    def finalize_local_alias_action(self, command: CreateLocalAliasAction
                                    ) -> LocalAliasActionRecord: ...
    def transition_local_alias_action(self, command: TransitionLocalAliasAction
                                      ) -> LocalAliasActionRecord: ...
    def reconcile_startup(self) -> RecoveryReport: ...
```

Open the same DB with `foreign_keys=ON`, `journal_mode=WAL`, and `synchronous=FULL`. Store immutable payload bytes and keyed HMAC digests with `key_id`. Keep current JSON chat runs as a derived cache only. `ensure_local_alias_catalog` inserts/validates exactly desktop/Documents/downloads definitions and their opaque IDs/revisions without opening an alias; any unknown prior local row yields `MIGRATION_REVIEW_REQUIRED`. Map observation/grant/action rows exactly to the addendum fields and durable foreign keys; reject any local `WorkspaceGrant`, path, owner kind or category input. Wire this `IntentStore` as the production `LocalAliasRepository` dependency for Task 3/5 only after `EffectGate` schema-v3 migration/reconciliation completes. IntentStore transaction methods call existing EffectGate assertions at their prescribed boundary; they do not reimplement effects, STOP, worker ownership, schema-v3 migration or startup effect reconciliation.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the two commands from Step 2, then `"$PYTHON" tests/test_store_lifecycle.py` and `"$PYTHON" tests/test_protocol_state_store.py` as unchanged durable-schema conformance.
Expected: all tests `PASS`; every failpoint recovers one resource or explicit terminal/uncertain state, local-alias rows satisfy the durable v3 constraints, and no duplicate schema authority exists.

- [ ] **Step 5: Commit the durable intent store**

```bash
git add console/intent_store.py console/server.py tests/test_intent_store.py tests/test_local_alias_store.py
git commit -m "feat: persist routed actions and transport outbox"
```

### Task 7: Migrate legacy chat JSON and quarantine ambiguous legacy attachments

**Files:**
- Modify: `console/intent_store.py`
- Modify: `console/chat.py:199-300,846-908`
- Modify: `console/attachments.py:166-450`
- Create: `tests/test_legacy_chat_migration.py`
- Create: `tests/test_legacy_attachment_quarantine.py`

**Interfaces:**
- Consumes: Task 6 migration/reconciliation tables and existing `chat-runs.json`/attachment records.
- Produces: compiled `LegacyEvidencePolicy`, `LegacyDestinationEvidence`, `LegacyAttachmentQuarantine`, per-record reconciliation IDs/tombstones, and idempotent locked import.

- [ ] **Step 1: Write failing policy-precedence and quarantine tests**

```python
class LegacyEvidencePolicyTest(unittest.TestCase):
    def test_legacy_policy_never_promotes_status_text_to_delivery(self):
        cases = [
            ("truncated.json", "MIGRATION_REVIEW_REQUIRED"),
            ("completed_unversioned.json", "legacy_reconciliation_only"),
            ("failed_uncertain.json", "legacy_reconciliation_only"),
            ("canonical_without_receipt.json", "legacy_reconciliation_only"),
            ("root_provisional.json", "UNBOUND_LEGACY_DELIVERY_UNCERTAIN"),
        ]
        for fixture, category in cases:
            with self.subTest(fixture=fixture):
                self.assertEqual(migrate_fixture(fixture).category, category)

    def test_ambiguous_attachment_is_non_dispatchable_and_non_collectable(self):
        record = self.quarantine.import_ambiguous(legacy_file())
        self.assertEqual(record.state, "REVIEW_REQUIRED")
        self.assertFalse(record.dispatchable)
        self.assertFalse(record.collectable)
```

Cover fully linked supported receipts, pre-delivery allowlist, unknown/contradictory/unlinked rows, multiple root records, canonical-only blocking, unbound new-conversation blocking, source digest marker, crash/second start, ambiguous ownership, root/parent/leaf device+inode+size+digest evidence, and malformed envelope disabling writer traffic.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_legacy_chat_migration.py
"$PYTHON" tests/test_legacy_attachment_quarantine.py
```
Expected: `FAIL`; current JSON loader has no versioned evidence policy or quarantine state machine.

- [ ] **Step 3: Implement evidence-based one-time import**

```python
class LegacyEvidencePolicy:
    version = 1
    def classify(self, source: Mapping[str, object]) -> LegacyClassification: ...
```

Use precedence: invalid envelope; row contradiction; fully linked delivery receipt; fully linked pre-delivery receipt; otherwise reconciliation. Never fill missing historical evidence from current extension/account/surface identity. Quarantine uncertain files under the verified owner-only root and expose deletion only when all persisted identities prove confinement.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the two commands from Step 2.
Expected: all tests `PASS`; migration is locked/idempotent, affected writes remain blocked, global slots remain free, and zero migrated record creates an outbox or modern binding.

- [ ] **Step 5: Commit migration and quarantine**

```bash
git add console/intent_store.py console/chat.py console/attachments.py tests/test_legacy_chat_migration.py tests/test_legacy_attachment_quarantine.py
git commit -m "feat: migrate uncertain legacy deliveries safely"
```

### Task 8: Enroll the fixed extension identity and require signed surface/account proofs

**Files:**
- Modify: `chrome-extension/manifest.json`
- Modify: `chrome-extension/protocol.js`
- Modify: `chrome-extension/service-worker.js`
- Modify: `chrome-extension/service-worker-core.js`
- Modify: `chrome-extension/chatgpt-content.js`
- Modify: `chrome-extension/cortex-content.js`
- Modify: `console/chrome_extension.py:1-360`
- Modify: `transport/browser_chrome_extension.py:292-969`
- Modify: `chrome-extension/tests/extension.test.mjs`
- Modify: `tests/test_chrome_extension_bridge.py`
- Modify: `tests/test_chrome_extension_driver.py`

**Interfaces:**
- Consumes: Task 6 durable enrollment/dispatch-ledger records and `ChromeExtensionManager.command(..., permit=...)` from the effect plan.
- Produces: protocol v3 enrollment/pairing, `DestinationBinding`, `LiveTransportSession`, signed `SurfaceProof`, `command.prepare`, `command.execute`, and bounded authenticated provisional dispatch ledger.

- [ ] **Step 1: Add failing extension identity and two-phase tests**

```js
test("fixed extension enrollment survives worker restart and rejects replacement identity", async () => {
  const enrolled = await enrollExpectedExtension();
  assert.equal(enrolled.privateKey.extractable, false);
  await restartServiceWorker();
  assert.equal((await signPairingChallenge()).publicKeyFingerprint, enrolled.fingerprint);
  await assert.rejects(() => selfDeclareReplacementKey(), /EXTENSION_IDENTITY_REJECTED/);
});

test("prepare is read-only and execute consumes one exact fresh proof", async () => {
  const proof = await prepare(commandTuple());
  assert.equal(domMutations.length, 0);
  await execute(proof, commandTuple());
  assert.equal(domMutations.length, 1);
  await assert.rejects(() => execute(proof, commandTuple()), /PROOF_REPLAY/);
});
```

Cover exact manifest key/extension ID and Origin, generic-origin rejection, one-time 256-bit token, Ed25519 IndexedDB non-exportable key, instance/storage generations, non-exportable fingerprint key, no raw account identifier outside extension, signed challenge, backend/worker/reload/account/fingerprint-version restart cases, five-second proof freshness, every tuple field, work/unknown/localized/missing DOM, and older clients read-only.

- [ ] **Step 2: Run extension/backend tests to prove RED**

Run:
```bash
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_bridge.py
"$PYTHON" tests/test_chrome_extension_driver.py
```
Expected: `FAIL`; protocol v2 trusts a generic extension Origin/token and has no durable enrollment, signed proof, or prepare/execute split.

- [ ] **Step 3: Implement fixed identity, proof, and provisional ledger**

```ts
interface SurfaceProof {
  version: 1;
  pairingSessionId: string;
  commandId: string;
  dispatchAttemptId: string;
  tabId: number;
  windowId: number;
  observedUrl: string;
  payloadDigest: string;
  accountFingerprint: string;
  surface: "classic_chat";
  authorizationEpoch: number;
  consentVersion: number;
  nonce: string;
  observedAt: number;
  signature: string;
}
```

Pin the manifest key and expected ID in backend build. Reserve ledger bytes/entry during `PREPARING_DISPATCH`; unresolved entries never evict. On first provisional delivery, bind canonical `/c/...` only from the same authenticated dispatch attempt. Backend invalidation fences offline proofs immediately; provisional tombstone synchronization gates the next prepare but never STOP acknowledgement.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2.
Expected: all tests `PASS`; prepare has zero DOM effect, execute is single-use, and any identity/surface/account mismatch blocks before insertion/click.

- [ ] **Step 5: Commit extension identity protocol**

```bash
git add chrome-extension/manifest.json chrome-extension/protocol.js chrome-extension/service-worker.js chrome-extension/service-worker-core.js chrome-extension/chatgpt-content.js chrome-extension/cortex-content.js console/chrome_extension.py transport/browser_chrome_extension.py chrome-extension/tests/extension.test.mjs tests/test_chrome_extension_bridge.py tests/test_chrome_extension_driver.py
git commit -m "feat: enroll and attest the Chrome extension"
```

### Task 9: Finalize exact chat, GeneralMission, or LocalAliasAction through disjoint transactions

**Files:**
- Modify: `console/intent_router.py`
- Modify: `console/intent_store.py`
- Modify: `console/chat.py:136-215,348-595`
- Modify: `console/missions.py:345-480,872-970`
- Create: `tests/test_intent_finalization.py`
- Modify: `tests/test_chat_mission_pool_sharing.py`
- Modify: `tests/test_missions_api.py`
- Inspect for conformance only: `console/server.py`
- Run without modification: `tests/test_effect_gate_routes.py`, `tests/test_executor_runtime_truth.py`

**Interfaces:**
- Consumes: live route/handle from Task 4, Task 3 vault/local catalogs and current access observation, Task 6 atomic store, `StorageContract.assert_runtime_ready()`, consent/STOP/authorization epoch from `EffectGate`, Task 8 destination identity, and durable raw-request `410 LEGACY_TASK_ENDPOINT_DISABLED` tombstones.
- Produces: discriminated `POST /api/intent/routes/{route_id}/finalize`; writer-only `POST /api/intent/final-actions/{id}/admit-writer`; `POST /api/intent/final-actions/{id}/cancel`; `GeneralMission`; vault-only `GeneralMissionGrant`; `LocalAliasGrant`; `LocalAliasActionRecord`; and `LocalAliasActionService.finalize(...)`.

- [ ] **Step 1: Write failing finalization, idempotency, and capacity tests**

```python
class IntentFinalizationTest(unittest.IsolatedAsyncioTestCase):
    async def test_exact_chat_finalization_keeps_original_bytes_and_waits_for_admission(self):
        draft = "  ligne 1\nligne 2  "
        route = await route_exact_chat(self.client, draft)
        result = await finalize(self.client, route, key=IDEMPOTENCY_KEY, action="send_exact_chat")
        self.assertEqual(result["writerState"], "WAITING_FOR_WRITER")
        row = self.intent_store.chat_run(result["resourceId"])
        self.assertEqual(row.exact_draft_bytes, draft.encode())
        self.assertFalse(self.intent_store.outbox_for(row.id).eligible)
        self.assertEqual(self.extension.commands, [])

    async def test_general_mission_finalization_persists_vault_grant_and_outbox(self):
        route = await route_general_vault_mission(self.client)
        first = await finalize_general_mission(self.client, route, IDEMPOTENCY_KEY)
        second = await finalize_general_mission(self.client, route, IDEMPOTENCY_KEY)
        self.assertEqual(second, first)
        self.assertEqual(self.intent_store.count_for_route(route["decision_digest"]), 1)
        self.assertEqual(
            self.intent_store.general_mission(first["resourceId"]).workspace_ref.kind,
            "vault",
        )
        self.assertEqual(
            self.intent_store.mission(first["resourceId"]).routed_contract_bytes,
            route["preflight"]["cloud_payload_preview"].encode(),
        )

    async def test_local_alias_finalization_creates_only_grant_and_action(self):
        route = await route_verified_desktop_action(self.client)
        before = self.frozen_world.external_counters()
        result = await finalize(self.client, route, key=IDEMPOTENCY_KEY,
                                action="start_local_alias_action")
        self.assertEqual(result["executionClass"], "local_alias_action")
        self.assertEqual(result["state"], "awaiting_approval")
        self.assertEqual(self.intent_store.count("local_alias_grants"), 1)
        self.assertEqual(self.intent_store.count("local_alias_actions"), 1)
        self.assertEqual(self.frozen_world.external_counters(), before)
        self.assertTrue(zero_counts(
            "missions", "writers", "outboxes", "uploads",
            "browserCommands", "extensionLedger", "genericExecutor",
        ))
```

Cover changed digest/action/execution class/handle/catalog revision/alias/leaf/access observation/preview, cross-conversation route, route expiry after durable result, same/different key, simultaneous finalizations, and exact-Origin/UI-session fences. General mission cases cover vault-only handle, two writer slots, duplicate active destination, third waiting resource, explicit retry/cancel, restart never auto-admitting, provisional rekey collision/detachment and attachment rejection. Local cases cover access expiry/STOP/consent/epoch/storage/revision changes, no protected-alias open, no client alias/leaf/path authority, no writer admission endpoint, and exactly one grant/action with zero mission/chat/outbox/upload/browser/extension/generic-executor effect.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_finalization.py
"$PYTHON" tests/test_chat_mission_pool_sharing.py
"$PYTHON" tests/test_missions_api.py
```
Expected: `FAIL`; finalization does not yet discriminate vault general missions from local alias actions or create the exact local grant/action transaction.

- [ ] **Step 3: Implement authoritative finalization and writer CAS**

```python
class FinalizeChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["send_exact_chat"]
    conversation_handle: Token43
    decision_digest: Digest
    upload_id: Token43 | None = None

class FinalizeMissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start_mission"]
    conversation_handle: Token43
    catalog_entry_id: str
    catalog_revision: int
    decision_digest: Digest

class FinalizeLocalAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel,
                              populate_by_name=True)
    action: Literal["start_local_alias_action"]
    conversation_handle: Token43
    catalog_entry_id: str
    catalog_revision: int
    decision_digest: Digest

@dataclass(frozen=True, slots=True)
class GeneralMissionGrant:
    grant_id: str
    catalog_entry_id: str
    catalog_revision: int
    workspace_identity: WorkspaceIdentity
    operation_scope: OperationScope

@dataclass(frozen=True, slots=True)
class GeneralMission:
    mission_id: str
    workspace_ref: VaultWorkspaceRef
    grant: GeneralMissionGrant

@dataclass(frozen=True, slots=True)
class LocalAliasActionRecord:
    action_id: str
    route_digest: str
    grant_id: str
    alias: LocalAlias
    operation: Literal["create_directory"]
    allowed_leaf: str
    payload_digest: str
    stop_epoch: int
    authorization_epoch: int
    state: Literal["awaiting_approval", "active", "created", "failed_safe",
                   "outcome_unclear", "cancelled_by_stop"]
    created_inode: int | None
    terminal_code: str | None

class LocalAliasActionService:
    def finalize(self, *, route_id: str, conversation_handle: str,
                 catalog_entry_id: str, catalog_revision: int,
                 decision_digest: str) -> LocalAliasActionRecord: ...
```

The server reconstructs the class and all authority solely from the consumed route. `GeneralMission` finalization accepts only `VaultWorkspaceRef`, calls `StorageContract.open()/open_workspace()`, derives one vault grant from the verified handle, and commits grant/mission/contract outbox atomically; admission separately CASes waiting→active and creates one writer lease. `LocalAliasActionService.finalize` never opens the alias: under one immediate transaction it checks exact Origin/session/handle/route/action/digest/catalog/alias/leaf, fresh storage readiness, STOP/authorization epoch and matching unexpired observation identity, then creates exactly one `LocalAliasGrant` and one `LocalAliasActionRecord(awaiting_approval)`. Byte-identical idempotent retry returns the canonical record; changed action/digest conflicts. Do not edit the durable-owned legacy task POST tombstones.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2, then run the unchanged conformance suites:
```bash
"$PYTHON" tests/test_effect_gate_routes.py
"$PYTHON" tests/test_executor_runtime_truth.py
```
Expected: all tests `PASS`; general missions alone can allocate mission/writer/outbox resources, local action finalization allocates only its grant/action, and durable-owned legacy mutations remain effect-free raw-request 410 tombstones.

- [ ] **Step 5: Commit finalization and admission**

```bash
git add console/intent_router.py console/intent_store.py console/chat.py console/missions.py tests/test_intent_finalization.py tests/test_chat_mission_pool_sharing.py tests/test_missions_api.py
git commit -m "feat: finalize disjoint mission and local action routes"
```

### Task 10: Stream exact-chat attachments through durable upload leases

**Files:**
- Modify: `console/intent_router.py`
- Modify: `console/intent_store.py`
- Modify: `console/attachments.py:1-450`
- Modify: `frontend/lib/api.ts:1-51`
- Create: `tests/test_intent_uploads.py`
- Modify: `tests/test_attachment_boundaries.py`
- Modify: `tests/test_mission_attachment_contract.py`

**Interfaces:**
- Consumes: route/final-action idempotency, `EffectGate` direct intent/activation, Task 1 `AttachmentDescriptor`, and verified private upload-root descriptors.
- Produces: reserve/raw PUT/status/finalize/cancel/abandon APIs and `UploadLease` state `RESERVED -> STREAMING -> FSYNCED -> CLAIMED -> RELEASED`.

- [ ] **Step 1: Write failing upload authority, state, and crash tests**

```python
class IntentUploadTest(unittest.IsolatedAsyncioTestCase):
    async def test_reserve_and_raw_put_create_no_outbox_or_writer(self):
        action = await reserve_upload(self.client, self.route, token=UPLOAD_TOKEN)
        await put_raw(self.client, action.upload_id, FILE_BYTES, token=UPLOAD_TOKEN)
        self.assertEqual(self.intent_store.upload(action.upload_id).state, "FSYNCED")
        self.assertEqual(self.intent_store.count("message_outbox"), 0)
        self.assertEqual(self.intent_store.count("conversation_writer_leases"), 0)

    async def test_upload_token_is_required_before_file_open_or_state_change(self):
        for header in (None, "wrong-token"):
            with self.subTest(header=header):
                before = upload_root_snapshot()
                response = await self.client.put(
                    URL, content=FILE_BYTES, headers=upload_headers(header),
                )
                self.assertIn(response.status_code, {401, 403})
                self.assertEqual(upload_root_snapshot(), before)
```

Inject crashes between reservation, `O_EXCL`, inode receipt, stream heartbeat, fsync, parent fsync, `FSYNCED`, claim/queue/outbox transaction, and response. Cover byte overrun/underrun, hard limit, MIME/digest/metadata mismatch, response loss after FSYNCED, no append/resume, 30-minute inactivity, two-hour cap, STOP/consent/cancel, collector mutex/CAS, unbound-file quarantine, wrong/missing token on PUT/GET/finalize/cancel, token redaction, renderer token loss, abandonment/finalization race, and exactly one upload/resource/outbox.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_uploads.py
"$PYTHON" tests/test_attachment_boundaries.py
"$PYTHON" tests/test_mission_attachment_contract.py
```
Expected: `FAIL`; current attachment endpoint accepts base64 JSON and lacks token-fenced raw streaming and durable leases.

- [ ] **Step 3: Implement reserve, raw stream, lookup, finalization, cancel, and token-loss abandonment**

```python
@router.post("/routes/{route_id}/uploads/reserve")
async def reserve_upload(route_id: str, body: ReserveUploadRequest,
                         idempotency_key: IdempotencyKeyHeader,
                         upload_authorization: UploadAuthorizationHeader) -> UploadReserveResponse: ...

@router.put("/uploads/{upload_id}")
async def upload_raw(upload_id: str, request: Request,
                     upload_authorization: UploadAuthorizationHeader) -> UploadStateResponse: ...

@router.get("/uploads/{upload_id}")
async def upload_status(upload_id: str, upload_authorization: UploadAuthorizationHeader) -> UploadStateResponse: ...
```

Store only token HMAC. Open an unpredictable one-component name relative to a verified private root with `O_CREAT|O_EXCL|O_NOFOLLOW`, persist observed device/inode separately from expected descriptor, heartbeat durably, fsync file/parent, and claim only in the atomic `FSYNCED -> CLAIMED`, `UPLOADING -> QUEUED`, one-outbox transaction. `abandon-lost-upload` requires current UI session, fresh handle, state version, and `TOKEN_LOST`; it can only terminalize a still non-dispatchable resource.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2.
Expected: all tests `PASS`; partial or uncertain bytes never become queued, resumed, sent, or collected while referenced.

- [ ] **Step 5: Commit durable uploads**

```bash
git add console/intent_router.py console/intent_store.py console/attachments.py frontend/lib/api.ts tests/test_intent_uploads.py tests/test_attachment_boundaries.py tests/test_mission_attachment_contract.py
git commit -m "feat: stream routed chat attachments safely"
```

### Task 11: Dispatch immutable outbox messages through fenced prepare/execute

**Files:**
- Modify: `console/intent_store.py`
- Modify: `console/chrome_extension.py:54-342`
- Modify: `console/chat.py:301-498`
- Modify: `console/missions.py:455-807,1207-1316`
- Modify: `transport/browser_chrome_extension.py:292-969`
- Modify: `orchestration/runner.py:28-231`
- Modify: `orchestration/loop.py:68-880`
- Create: `tests/test_intent_dispatch.py`
- Modify: `tests/test_transport_session_isolation.py`
- Modify: `tests/test_runner_mode_a.py`
- Modify: `tests/test_loop_mock.py`

**Interfaces:**
- Consumes: Task 6 outbox/writer/dispatch records, Task 8 proof protocol, and effect-plan permits on every browser command.
- Produces: `OutboxDispatcher.prepare(message_id)`, `.execute(preparation_id, proof)`, `.record_receipt(...)`, `.invalidate_pre_effect(...)`; mission `CONTRACT`, `ITERATION_REPORT`, and `FOLLOW_UP` immutable messages.

- [ ] **Step 1: Write failing atomic-boundary and mission-message tests**

```python
class IntentDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_proof_consume_preparation_execute_and_dispatching_commit_together(self):
        preparation = await self.dispatcher.prepare(MESSAGE_ID)
        proof = await self.extension.prepare(preparation)
        receipt = await self.dispatcher.execute(preparation.id, proof)
        self.assertEqual(receipt.outbox_state, "DISPATCHING")
        self.assertEqual(self.intent_store.preparation(preparation.id).state, "EXECUTING")
        self.assertTrue(self.intent_store.proof(proof.nonce).consumed)

    async def test_multicycle_mission_persists_each_kind_once(self):
        await self.loop.run_three_cycles()
        rows = self.intent_store.outbox_for_resource(self.loop.mission_id)
        self.assertEqual([(r.sequence, r.kind) for r in rows], [
            (1, "CONTRACT"), (2, "ITERATION_REPORT"), (3, "FOLLOW_UP"),
        ])
        self.assertTrue(all(
            r.payload_bytes == r.original_persisted_bytes for r in rows
        ))
```

Failpoints cover READY claim, ledger reservation, signed proof, before/after atomic dispatch boundary, before execute, after execute/click, visible message, receipt commit, crash/restart, STOP/consent/identity/lease in PREPARING versus DISPATCHING, crossed pairs, stale writer/dispatch fences, canonical/provisional and online/offline matrices, and no regenerated or direct mission transport.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_dispatch.py
"$PYTHON" tests/test_transport_session_isolation.py
"$PYTHON" tests/test_runner_mode_a.py
"$PYTHON" tests/test_loop_mock.py
```
Expected: `FAIL`; current chat and mission loops call transport directly and do not persist a typed immutable outbox/preparation.

- [ ] **Step 3: Implement one outbox dispatcher and remove direct transport calls**

```python
class OutboxDispatcher:
    async def prepare(self, message_id: str) -> DispatchPreparation: ...
    async def execute(self, preparation_id: str, proof: SurfaceProof) -> DispatchingReceipt: ...
    async def record_receipt(self, message_id: str, receipt: SignedDeliveryReceipt) -> DeliveredReceipt: ...
    async def invalidate_pre_effect(self, message_id: str, reason: str) -> PreDeliveryFailure: ...
```

Generate report bytes once from sanitized relative evidence and persist before scheduling. The mission loop waits for each message's durable outcome. PREPARING invalidation advances attempt generation and consumes/tombstones proof before retry; only generic crash/lease plus explicit user retry can create a fresh attempt. DISPATCHING without receipt becomes uncertain and releases the writer while blocking only that conversation.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the four commands from Step 2.
Expected: all tests `PASS`; every extension command validates current writer/dispatch/effect fences and no mission report is regenerated or replayed.

- [ ] **Step 5: Commit durable dispatch**

```bash
git add console/intent_store.py console/chrome_extension.py console/chat.py console/missions.py transport/browser_chrome_extension.py orchestration/runner.py orchestration/loop.py tests/test_intent_dispatch.py tests/test_transport_session_isolation.py tests/test_runner_mode_a.py tests/test_loop_mock.py
git commit -m "feat: dispatch immutable fenced outbox messages"
```

### Task 12: Execute LocalAliasAction through the fixed blocked worker and EffectGate

**Files:**
- Modify: `console/local_alias_actions.py`
- Modify: `console/intent_store.py`
- Modify: `console/intent_router.py`
- Create: `tests/test_local_alias_action_service.py`
- Run without modification: `tests/test_local_alias_worker.py`, `tests/test_local_alias_worker_runner.py`, `tests/test_effect_gate.py`, `tests/test_store_lifecycle.py`, `tests/test_executor_tools.py`

**Interfaces:**
- Consumes unchanged: Task 9 `LocalAliasGrant/LocalAliasActionRecord`; `StorageContract.assert_runtime_ready() -> StorageStatus`; durable `LocalAliasApprovalChallenge/Response/Receipt`; `EffectGate.register_local_alias_approval(*, action_id: str, grant_id: str, catalog_entry_id: str, catalog_revision: int, alias: LocalAlias, operation: Literal["create_directory"], allowed_leaf: str, payload_digest: str, authorization_epoch: int) -> LocalAliasApprovalChallenge`; `.decide_approval(response: ApprovalResponse) -> ApprovalReceipt`; `.local_alias_approval_receipt(*, action_id: str, epoch: int, arguments_digest: str) -> LocalAliasApprovalReceipt`; `.begin_local_alias_intent(*, action_id: str, epoch: int, operation: Literal["create_directory"], payload_digest: str, grant_id: str) -> EffectIntent`; `.record_blocked_ownership`; `.activate_local_alias_intent(effect_id: str, *, approval: LocalAliasApprovalReceipt, blocked_worker_permit: BlockedWorkerActivationPermit) -> EffectActivation`; `.succeed/.fail/.outcome_unclear`; durable `LocalAliasWorkerRequest/Receipt`; `LocalAliasWorkerRunner(effect_gate: EffectGate, installed_home: Path, storage_contract: StorageContract)`, `.spawn_blocked(*, request: LocalAliasWorkerRequest, intent: EffectIntent) -> BlockedLocalAliasWorker`, `.assert_pre_activation_ready(*, intent: EffectIntent) -> BlockedWorkerActivationPermit`, `.run(*, request: LocalAliasWorkerRequest, activation: EffectActivation, deadline_seconds: Literal[60] = 60) -> LocalAliasWorkerReceipt`, `.abort_blocked(*, intent: EffectIntent, code: str) -> None`; and durable startup reconciliation result. It consumes no `WorkspaceHandle`, `ToolExecutor`, `MissionLoop`, process tool, browser transport or generic registry.
- Produces: exact `LocalAliasActionService.prepare_approval(action_id) -> LocalAliasApprovalChallenge`, `await .execute(action_id, approval: LocalAliasApprovalReceipt)`, `.reconcile_startup(action_id)`; distinct `POST /api/local-alias-actions/{action_id}/prepare-approval` and `POST /api/local-alias-actions/{action_id}/approval`; and state transitions `awaiting_approval|active|created|failed_safe|outcome_unclear|cancelled_by_stop`. No local approval payload contains `missionId`, owner kind or category.

- [ ] **Step 1: Write failing activation-order, negative-capability, and outcome tests**

```python
class LocalAliasActionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_create_spawns_blocked_then_activates_then_releases(self):
        action = finalized_local_action(alias="desktop", leaf="cortex-live-test")
        approval = approve_exact_local_action(action)
        result = await self.service.execute(action_id=action.action_id, approval=approval)
        self.assertEqual(self.trace, [
            "intent-fsynced", "runner-spawn-readiness", "spawned-blocked",
            "ownership-fsynced", "runner-pre-activation-ready", "permit-issued",
            "activation-received-permit", "effect-active",
            "runner-pre-release-ready", "released", "mkdirat",
            "receipt-fsynced", "child-closed-reaped",
        ])
        self.assertEqual(self.runner.readiness_barrier_count, 3)
        permit = self.runner.issued_permits[0]
        self.assertIs(
            self.effect_gate.local_activation_calls[0].blocked_worker_permit,
            permit,
        )
        self.assertEqual(
            self.runner.binding_for(permit),
            (effect_intent().effect_id, owned_process_identity(), STORAGE_TRANSACTION_ID, STOP_EPOCH),
        )
        self.assertEqual((result.state, result.created_inode), ("created", 4242))
        self.assertTrue(zero_counts(
            "missions", "writers", "outboxes", "uploads",
            "browser_commands", "extension_ledger", "generic_tools",
        ))

    async def test_existing_target_terminalizes_active_effect_without_mkdir(self):
        for target_kind in ("directory", "file", "symlink", "dangling_symlink"):
            with self.subTest(target_kind=target_kind):
                self.reset_target_fixture()
                create_target(target_kind)
                result = await self.service.execute(
                    action_id=ACTION_ID,
                    approval=approve_exact_local_action(ACTION_ID),
                )
                self.assertEqual(result.state, "failed_safe")
                self.assertEqual(result.terminal_code, "TARGET_ALREADY_EXISTS")
                self.assertEqual(self.worker.mkdirat_calls, [])

    async def test_stop_winning_before_activation_awaits_abort_and_reap(self):
        self.barrier.pause_after("ownership-fsynced")
        execution = asyncio.create_task(self.service.execute(
            action_id=ACTION_ID, approval=approve_exact_local_action(ACTION_ID),
        ))
        await self.barrier.reached()
        await request_and_settle_stop()
        self.barrier.release()
        result = await execution
        self.assertEqual(result.state, "cancelled_by_stop")
        self.assertEqual(self.runner.abort_blocked_calls, [
            (effect_intent(), "LOCAL_ACTION_CANCELLED_BY_STOP"),
        ])
        self.assertTrue(self.runner.abort_awaited)
        self.assertTrue(self.runner.child_closed_and_reaped)
        self.assertEqual(self.worker.release_count, 0)
        self.assertEqual(self.worker.mkdirat_calls, [])

    async def test_readiness_loss_at_each_gate_aborts_without_release(self):
        phases = {"spawn": 1, "before_activation": 2, "before_release": 3}
        for loss in ("detach", "transition", "rollback", "lease"):
            for phase, expected_calls in phases.items():
                with self.subTest(loss=loss, phase=phase):
                    self.reset_execution_fixture(readiness_loss=loss, failure_phase=phase)
                    result = await self.service.execute(
                        action_id=ACTION_ID,
                        approval=approve_exact_local_action(ACTION_ID),
                    )
                    self.assertEqual(result.terminal_code, "STORAGE_NOT_READY")
                    self.assertEqual(self.runner.readiness_barrier_count, expected_calls)
                    self.assertEqual(self.worker.release_count, 0)
                    self.assertEqual(self.worker.mkdirat_calls, [])
                    if phase == "spawn":
                        self.assertEqual(self.runner.spawn_calls, [])
                        self.assertEqual(self.effect_gate.local_activation_calls, [])
                    elif phase == "before_activation":
                        self.assertTrue(self.runner.abort_awaited)
                        self.assertEqual(self.effect_gate.local_activation_calls, [])
                    else:
                        self.assertTrue(self.runner.run_cleanup_awaited)
                        self.assertIsNotNone(
                            self.effect_gate.local_activation_calls[0].blocked_worker_permit,
                        )
                        self.assertEqual(result.state, "failed_safe")
                        self.assertEqual(self.effect_gate.effect_state(), "failed")
                        self.assertEqual(self.effect_gate.terminal_code(), "STORAGE_NOT_READY")
                    self.assertTrue(self.runner.child_closed_and_reaped)

    async def test_local_approval_cannot_cross_subject_digest_or_epoch(self):
        for mutation in ("other_action", "other_digest", "stale_epoch", "replayed_nonce"):
            with self.subTest(mutation=mutation):
                challenge = await prepare_local_alias_approval(self.client, ACTION_A)
                response = mutate_local_approval(challenge, mutation)
                refused = await self.client.post(
                    f"/api/local-alias-actions/{ACTION_A}/approval", json=response,
                )
                self.assertEqual(refused.status_code, 409)
                self.assertEqual(
                    self.intent_store.local_alias_action(ACTION_A).state,
                    "awaiting_approval",
                )
                self.assertEqual(self.intent_store.count("missions"), 0)
                self.assertEqual(self.runner.spawn_calls, [])
```

Cover exact action/grant/catalog revision/alias/leaf/digest/nonce/scope/STOP/authorization epoch matching; denial/expiry/reuse; readiness/access-observation recheck; two active ChatGPT writers not blocking or being changed; client owner/category/class/path rejection; worker attestation failure; STOP before/after spawn and activation; timeout/TCC denial/EOF/malformed receipt/cancellation/crash; home/alias replacement before final check, during/after `mkdirat`; exact receipt/inode/fsync; existing file/directory/symlink/dangling symlink; restart in every state; and zero listing/read/search/write-file/move/delete/process/network/upload/capture/chat/browser/extension/generic-executor path. Missing post-`mkdirat` proof is always `LOCAL_ACTION_OUTCOME_UNCLEAR` and never replayed or cleaned up.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_local_alias_action_service.py
```
Expected: `FAIL`; intent has no `LocalAliasActionService` execution/approval orchestration over the durable blocked runner.

- [ ] **Step 3: Implement the exact service and blocked-child effect ordering**

```python
class LocalAliasActionService:
    def finalize(self, *, route_id: str, conversation_handle: str,
                 catalog_entry_id: str, catalog_revision: int,
                 decision_digest: str) -> LocalAliasActionRecord: ...
    def prepare_approval(self, action_id: str) -> LocalAliasApprovalChallenge: ...
    async def execute(self, *, action_id: str,
                      approval: LocalAliasApprovalReceipt) -> LocalAliasActionRecord: ...
    def reconcile_startup(self, action_id: str) -> LocalAliasActionRecord: ...

local_action_router = APIRouter(prefix="/api/local-alias-actions")

@local_action_router.post("/{action_id}/prepare-approval")
async def prepare_local_alias_approval(action_id: str) -> LocalAliasApprovalChallenge: ...

@local_action_router.post("/{action_id}/approval")
async def decide_and_execute_local_alias_action(
    action_id: str, body: LocalAliasApprovalResponse,
) -> LocalAliasActionRecord: ...
```

`prepare_approval` reloads the exact grant/action/readiness/access observation, recomputes the canonical payload digest from those rows, and calls only `register_local_alias_approval(action_id=..., grant_id=..., catalog_entry_id=..., catalog_revision=..., alias=..., operation="create_directory", allowed_leaf=..., payload_digest=..., authorization_epoch=...)`. The central gate supplies scope `once`, STOP epoch and nonce. The approval route requires `path action_id == body.action_id`, rejects extra/client authority fields, recomputes the digest, converts to `LocalAliasApprovalResponse(action_id, epoch, arguments_digest, nonce, scope="once", approve)`, calls the same `EffectGate.decide_approval` used by missions, then loads `local_alias_approval_receipt(action_id=..., epoch=..., arguments_digest=...)`; it never fabricates a mission ID or a parallel nonce table.

`execute` revalidates the typed receipt and observation, persists/fsyncs the local intent through `begin_local_alias_intent`, constructs the exact worker request, then invokes `spawn_blocked(request=request, intent=intent)`; `LocalAliasWorkerRunner.spawn_blocked()` is the sole owner of the pre-spawn `StorageContract.assert_runtime_ready()` barrier and spawns no child on failure. After blocked ownership is durable the service obtains `permit = runner.assert_pre_activation_ready(intent=intent)` inside the serialized effect transaction; the durable runner binds it to the exact effect, owned PID/PGID/start identity, storage transaction/readiness observation and authorization/STOP epoch. Only that same object may call `activate_local_alias_intent(intent.effect_id, approval=approval, blocked_worker_permit=permit)`; no local action activation omits it. `runner.run(request=request, activation=activation, deadline_seconds=60)` owns the third readiness barrier immediately before child release. A detach, transition, rollback, contradictory status or managed-start lease loss before activation aborts without release. Failure after activation but before release terminalizes the action `failed_safe` and effect `failed/STORAGE_NOT_READY`, closes/reaps the worker and proves zero `mkdirat` or other mutation. A `finally` executes `await runner.abort_blocked(intent=intent, code=terminal_code)` whenever control did not yield to `run`, then verifies the exact PID/PGID/start identity is closed and reaped before returning. Map every other bounded durable receipt to `created|failed_safe|outcome_unclear|cancelled_by_stop`; never inspect/reopen an absolute alias path in the service. `reconcile_startup` only maps the durable reconciler result to the local action row and never invokes a worker mutation.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the command from Step 2, then the unchanged durable conformance suites:
```bash
"$PYTHON" tests/test_local_alias_worker.py
"$PYTHON" tests/test_local_alias_worker_runner.py
"$PYTHON" tests/test_effect_gate.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_executor_tools.py
```
Expected: all tests `PASS`; one local action yields at most one durable worker effect after exact approval, STOP/crash outcomes are truthful, and generic executor/mission/browser surfaces remain unchanged.

- [ ] **Step 5: Commit the routed operation**

```bash
git add console/local_alias_actions.py console/intent_store.py console/intent_router.py tests/test_local_alias_action_service.py
git commit -m "feat: execute local alias actions through fixed worker"
```

### Task 13: Add delivery, local-action, legacy-record, and legacy-delete reconciliation

**Files:**
- Modify: `console/intent_router.py`
- Modify: `console/intent_store.py`
- Modify: `console/local_alias_actions.py`
- Modify: `console/attachments.py:324-450`
- Modify: `console/missions.py:1109-1357`
- Create: `tests/test_intent_reconciliation.py`
- Create: `tests/test_local_alias_reconciliation.py`
- Create: `tests/test_legacy_delete_reconciliation.py`
- Inspect for conformance only: `console/server.py`
- Run without modification: `tests/test_effect_gate_routes.py`

**Interfaces:**
- Consumes: Task 6 durable state versions, Task 7 quarantine identities, Task 11 immutable messages, Task 12 local action records, durable `reconcile_local_alias_effect` results, and durable-owned raw-request legacy-task 410 tombstones unchanged.
- Produces: strict CAS endpoints for message/legacy delivery, local-action outcome confirmation, legacy attachment disposition and read-only delete inspection. It never reopens an alias or invokes the worker's create operation during reconciliation.

- [ ] **Step 1: Write failing CAS, no-replay, and delete-capture tests**

```python
class IntentReconciliationTest(unittest.IsolatedAsyncioTestCase):
    async def test_opposing_message_reconciliation_has_one_winner_and_zero_outbox(self):
        delivered, not_delivered = await concurrently(
            reconcile_message("DELIVERED", version=7),
            reconcile_message("DEFINITIVE_NOT_DELIVERED", version=7),
        )
        self.assertEqual(
            sorted([delivered.status_code, not_delivered.status_code]), [200, 409],
        )
        self.assertEqual(self.intent_store.outbox_count_after_reconciliation(), 0)

    async def test_delete_worker_unlinks_only_durably_captured_matching_private_name(self):
        record = approved_quarantine_record()
        await self.worker.capture(record)
        self.assertEqual(record_state(record), "CAPTURED_MATCHED")
        await self.worker.delete(record)
        self.assertEqual(record_state(record), "DELETED")
        self.assertTrue(original_replacement_still_exists())

    async def test_active_local_action_maps_durable_unclear_without_retry(self):
        self.durable_reconciler.result = ReconcileResult(
            state="outcome_unclear", code="LOCAL_ACTION_OUTCOME_UNCLEAR",
        )
        result = self.service.reconcile_startup(LOCAL_ACTION_ID)
        self.assertEqual(result.state, "outcome_unclear")
        self.assertEqual(local_alias_worker_create_calls(), 0)
        self.assertEqual(generic_executor_calls(), 0)
```

Cover identical replay across restart, opposing/stale choices, provisional delivered forbidden without recovered binding, all CHAT/CONTRACT/ITERATION_REPORT/FOLLOW_UP previews and replacement semantics, general mission stays paused and reacquires writer, same-kind immutable replacement with `supersedes_message_id`, all durable local-action reconcile results (`created|failed_safe|outcome_unclear|cancelled_by_stop`) with zero re-execution, canonical/unbound legacy per-record unblock, keep/delete decisions, retention floor, root/parent/staging identity, capture replacement races, restore exclusive, `CAPTURED_MATCHED`, crash boundaries and read-only inspection.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_reconciliation.py
"$PYTHON" tests/test_local_alias_reconciliation.py
"$PYTHON" tests/test_legacy_delete_reconciliation.py
```
Expected: `FAIL`; strict state-version endpoints and dedicated capture/delete/inspection state machines do not exist.

- [ ] **Step 3: Implement exhaustive strict reconciliation endpoints**

```python
@router.post("/final-actions/{action_id}/messages/{message_id}/reconcile")
async def reconcile_message(action_id: str, message_id: str,
                            body: MessageReconciliationRequest) -> ReconciliationResponse: ...

@router.post("/legacy-attachments/{attachment_id}/inspect-delete-outcome")
async def inspect_delete_outcome(attachment_id: str,
                                 body: LegacyDeleteInspectionRequest) -> LegacyDeleteInspectionResponse: ...

@local_action_router.post("/{action_id}/reconcile")
async def reconcile_local_alias_action(
    action_id: str, body: LocalAliasReconciliationRequest,
) -> LocalAliasActionRecord: ...
```

Use state-version CAS and store canonical responses for identical replay. Local-action reconciliation accepts only the durable worker/effect reconciler result, maps it to the action row and never invokes `mkdirat`, worker create, generic executor, deletion or cleanup. Other reconciliation creates no outbox, binding, current identity, transport command or filesystem mutation. The legacy delete worker retains its separate verified capture/delete flow; the inspection endpoint remains read-only.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2, then `"$PYTHON" tests/test_effect_gate_routes.py`, `"$PYTHON" tests/test_local_alias_worker_runner.py`, and `"$PYTHON" tests/test_store_lifecycle.py` as read-only conformance.
Expected: all tests `PASS`; uncertain effects are inspected or explicitly reconciled, never guessed, retried, or attributed without evidence, and no reconciliation adapter changes the durable-owned legacy task tombstones.

- [ ] **Step 5: Commit reconciliation**

```bash
git add console/intent_router.py console/intent_store.py console/local_alias_actions.py console/attachments.py console/missions.py tests/test_intent_reconciliation.py tests/test_local_alias_reconciliation.py tests/test_legacy_delete_reconciliation.py
git commit -m "feat: reconcile uncertain routed and legacy effects"
```

### Task 14: Wire consent, STOP reset, direct/admin effects, and route-wide effect classification

**Files:**
- Modify: `console/intent_router.py`
- Modify: `console/settings.py:215-245`
- Modify: `console/onboarding.py:366-434`
- Modify: `console/chat.py:498-845`
- Modify: `console/attachments.py:248-356`
- Modify: `console/missions.py:807-855,1183-1357`
- Modify: `console/chrome_extension.py:185-342`
- Modify: `console/intent_store.py`
- Create: `tests/test_intent_safety_gate.py`
- Run without modification: `tests/test_effect_gate_routes.py`, `tests/test_direct_effect_recovery.py`, `tests/test_effect_gate.py`, `tests/test_local_alias_worker_runner.py`

**Interfaces:**
- Consumes: exact `EffectGate`, internal `EffectGate.reset_stop(*, expected_epoch: int) -> StopStatus`, `DirectEffectRequest`, `EffectActivation`, mission/local typed central approvals including `LocalAliasApprovalResponse/Receipt`, `StopStatus`, permits, schema-v3 effect inventory and HTTP `effect` contracts from the durable-effects plan.
- Produces: intent route adapters that pass those types unchanged; `POST /api/ui/session`; `POST /api/transport/stop-reset/prepare`; strict `POST /api/transport/stop-reset`; `StopResetChallenge`, `StopResetRequest`, and durable `StopResetReceipt`; and complete classified surface inventory. The simple durable-gate reset method is never exposed as the product HTTP contract.

- [ ] **Step 1: Write failing consent/STOP race and inventory tests**

```python
class IntentSafetyGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_stop_and_consent_races_have_one_authoritative_winner(self):
        boundaries = (
            "upload_reserve", "upload_open", "finalize", "writer_claim",
            "prepare_dispatch", "execute_dispatch", "mission_resume",
            "mission_approval", "local_access_spawn_blocked",
            "local_access_activation", "local_write_spawn_blocked",
            "local_write_activation",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                result = await run_both_orders(boundary, self.barrier)
                self.assertIn(
                    result.pre_effect_winner,
                    {"STOP", "CONSENT_WITHDRAWAL", "EFFECT"},
                )
                self.assertFalse(result.effect_after_authority_revocation)
                self.assertIn(result.possible_crossed_effect, {
                    False, "DELIVERY_UNCERTAIN", "LOCAL_ACTION_OUTCOME_UNCLEAR",
                })

    def test_every_route_tool_transport_and_extension_command_is_classified(self):
        self.assertEqual(
            self.effect_inventory.discovered, self.effect_inventory.registered,
        )

    def test_local_approval_body_has_no_mission_or_client_authority_fields(self):
        fields = LocalAliasApprovalResponse.model_fields
        self.assertEqual(set(fields), {
            "action_id", "epoch", "arguments_digest", "nonce", "scope", "approve",
        })
        self.assertTrue({"mission_id", "owner_kind", "category"}.isdisjoint(fields))

    async def test_stop_reset_is_session_nonce_cas_bound_and_exact_replay_is_idempotent(self):
        session = await bootstrap_ui_session(self.client, origin=FRONTEND_ORIGIN)
        challenge = await prepare_stop_reset(self.client, session=session)
        body = {
            "resetAttemptId": str(uuid.uuid4()),
            "expectedStateVersion": challenge["expectedStateVersion"],
            "expectedAuthorizationEpoch": challenge["expectedAuthorizationEpoch"],
            "nonce": challenge["nonce"],
        }
        first = await post_stop_reset(
            self.client, body, session=session, origin=FRONTEND_ORIGIN,
        )
        replay = await post_stop_reset(
            self.client, body, session=session, origin=FRONTEND_ORIGIN,
        )
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(
            durable_reset_receipt(body["resetAttemptId"]).response, first.json(),
        )
```

Cover durable authorization epoch and consent version at every listed boundary, restart order, no old authority restored, bodyless/simple `{expectedEpoch}` reset rejection, missing/wrong Origin or UI-session header, session expiry, two-minute expiry and single-use 256-bit nonce, attempt/digest replay before consumed-nonce validation, changed-digest attempt reuse, stale/concurrent state version or epoch, crash immediately before/after commit, reset no auto-retry/resume/consent, and settings/onboarding/direct upload/capture effect envelopes.

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_intent_safety_gate.py
```
Expected: `FAIL`; intent adapters do not yet pass the central mission/local approval, blocked-worker and reset contracts without adding client authority.

- [ ] **Step 3: Wire existing effect contracts without defining a second gate**

```python
class StopResetChallenge(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel,
                              populate_by_name=True)
    schema_version: Literal[1] = 1
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    expires_at: datetime
    expected_state_version: int = Field(ge=0)
    expected_authorization_epoch: int = Field(ge=0)

class StopResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel,
                              populate_by_name=True)
    reset_attempt_id: UUID
    expected_state_version: int = Field(ge=0)
    expected_authorization_epoch: int = Field(ge=0)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")

transport_router = APIRouter(prefix="/api/transport")

@transport_router.post("/stop-reset/prepare")
async def prepare_stop_reset(
    origin: ExactFrontendOrigin, ui_session: UiSessionHeader,
) -> StopResetChallenge: ...

@transport_router.post("/stop-reset")
async def reset_stop_from_ui(
    body: StopResetRequest, origin: ExactFrontendOrigin,
    ui_session: UiSessionHeader,
) -> StopResetReceipt: ...
```

Adapters translate camelCase JSON once into the frozen durable-plan types. Server registries, not clients, select owner kind/category. Mission approval HTTP retains `missionId`; local approval HTTP has only `actionId,epoch,argumentsDigest,nonce,scope,approve`, calls the same `decide_approval`, and reloads the canonical grant/action rows before execution. Obtain `EffectActivation` before any direct/admin temporary open, byte, publication or browser envelope. For fixed local access/create workers, first obtain the exact `BlockedWorkerActivationPermit` after durable ownership and pass the same object to the corresponding activation call; no adapter can construct, omit, substitute or reuse it. Low-level mutation functions require the returned activation, and `runner.run()` repeats readiness before release.

Bootstrap a random bounded UI session only for the exact configured Cortex frontend Origin, return its token once, keep it only in browser memory, disable credentials, and require it in `X-Cortex-UI-Session` on both reset calls. Preparation hashes and durably binds a fresh 32-byte nonce to that session, the displayed STOP state version, the authorization epoch, and an expiry exactly 120 seconds later. The reset wrapper takes the shared `Store` exclusive transaction, performs identical attempt/digest replay lookup before consumed-nonce validation, validates exact Origin/session/nonce/state-version/epoch, calls only internal `EffectGate.reset_stop(expected_epoch=body.expected_authorization_epoch)`, and atomically persists session ID, `reset_attempt_id`, canonical request digest, nonce digest, and canonical response before commit. A retry after a lost response or restart returns that byte-equivalent receipt; any changed digest, reused nonce under another attempt, stale fence, active/unclear effect, missing session header, or non-exact Origin fails closed without reset. No general CORS preflight may authorize this route.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the command from Step 2, then:
```bash
"$PYTHON" tests/test_effect_gate_routes.py
"$PYTHON" tests/test_direct_effect_recovery.py
"$PYTHON" tests/test_effect_gate.py
"$PYTHON" tests/test_local_alias_worker_runner.py
```
Expected: all tests `PASS`; discovered and registered mutation/sensitive surfaces are exactly equal, local approval cannot cross subject/digest/epoch or invent a mission, and every race ends in no effect or the correct explicit uncertain state.

- [ ] **Step 5: Commit safety adapters**

```bash
git add console/intent_router.py console/intent_store.py console/settings.py console/onboarding.py console/chat.py console/attachments.py console/missions.py console/chrome_extension.py tests/test_intent_safety_gate.py
git commit -m "feat: bind intent flows to durable safety gates"
```

### Task 15: Add per-conversation frontend routing, digest worker, provisional preparation, and input matrix

**Files:**
- Create: `frontend/lib/intent.ts`
- Create: `frontend/hooks/useIntentRouter.ts`
- Create: `frontend/workers/attachmentDigest.worker.ts`
- Create: `frontend/components/IntentClarificationPanel.tsx`
- Create: `frontend/components/IntentNoticePanel.tsx`
- Create: `frontend/components/IntentPreflightDialog.tsx`
- Modify: `frontend/lib/localAliasAction.ts`
- Modify: `frontend/components/LocalAliasActionPanel.tsx`
- Modify: `frontend/lib/api.ts:1-51`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/conversation-state.ts`
- Modify: `frontend/components/Composer.tsx:1-194`
- Modify: `frontend/components/ChatWorkspace.tsx:1-420`
- Modify: `frontend/components/CortexApp.tsx:251-1293`
- Create: `frontend/hooks/useIntentRouter.test.tsx`
- Create: `frontend/components/IntentPreflightDialog.test.tsx`
- Create: `frontend/components/LocalAliasActionIntegration.test.tsx`
- Modify: `frontend/components/Composer.test.tsx`
- Modify: `frontend/components/CortexApp.integration.test.tsx`

**Interfaces:**
- Consumes: Tasks 3/5/9/10/12 route, access prepare/execute, provisional, discriminated finalization, upload, writer admission, local approval/execute and cancel APIs; prior UI-plan `LocalAliasActionView/LocalAliasActionPanel` callbacks.
- Produces: per-conversation `IntentRoutingState`; `submitIntent(key, trigger)`, `answerClarification`, `finalizeChat`, `finalizeGeneralMission`, `verifyLocalAliasAccess`, `finalizeLocalAliasAction`, `approveAndExecuteLocalAliasAction`, `sendOnlyToChatGPT`, `cancelRoute`; worker `digestAttachment(file) -> AttachmentDescriptor`.

- [ ] **Step 1: Write failing composer/input-state tests**

```tsx
it.each([
  ["Enter text", "route"], ["Continuer text", "route"], ["text+file", "route"],
  ["file only", "chat_attachment"], ["Exécuter text", "manual_preflight"],
  ["Exécuter file", "local_notice"], ["capture", "capture"],
  ["routing disabled", "exact_chat"], ["router unavailable", "manual_choice"],
])("routes %s through %s", async (fixture, expected) => {
  const calls = await submitFixture(fixture);
  expect(calls.selectedPath).toBe(expected);
});

it("double Enter synchronously creates one route and one idempotency key", async () => {
  pressEnterTwice();
  expect(routeRequests).toHaveLength(1);
  expect(idempotencyKeys).toHaveLength(1);
});

it("runs a local alias route without any mission, writer, outbox, browser, or chat call", async () => {
  await submitExactDraft("cree moi un dossier cortex-live-test sur mon bureau");
  expect(localAliasPanel()).toHaveTextContent("Action locale");
  await clickVerifyAliasAccess();
  await clickFinalizeLocalAction();
  await approveAndExecuteLocalAction();
  expect(api.calls).toMatchObject({ route: 1, accessPrepare: 1, accessExecute: 1,
                                   localFinalize: 1, localApprovalPrepare: 1,
                                   localApproval: 1 });
  expect(api.calls).toMatchObject({ chat: 0, mission: 0, writer: 0, outbox: 0,
                                   browser: 0, extension: 0, executor: 0 });
});
```

Cover Shift+Enter, same function for Enter/Continuer, 150 ms no-flash threshold, classifying status, draft/file preservation, attachment add/remove/replace epoch/key invalidation, switch/edit/close abort, two conversations isolated, text+file digest off main thread, normal exact chat auto-finalizes without second click, and router-unavailable explicit choices. For local alias routes, cover zero request before the explicit access click, exact two-step access echo, access expiry/revision invalidation, finalization disabled until verified, one central local approval, created/failed/unclear mapping, draft preserved through denial/failure/uncertainty, no automatic retry, and `Envoyer seulement à ChatGPT` obtaining a fresh exact-chat route rather than reusing the local token.

- [ ] **Step 2: Run frontend tests to prove RED**

Run:
```bash
npm --prefix frontend run test:unit -- hooks/useIntentRouter.test.tsx components/IntentPreflightDialog.test.tsx components/LocalAliasActionIntegration.test.tsx components/Composer.test.tsx components/CortexApp.integration.test.tsx
```
Expected: `FAIL`; Enter currently calls direct send, composer has no route state, and new conversations are client-only provisional URLs.

- [ ] **Step 3: Implement per-conversation route state and accessible core panels**

```ts
export type IntentRoutingPhase =
  | "idle" | "classifying" | "clarifying" | "preflight" | "notice"
  | "verifying_alias_access" | "finalizing_local_action" | "awaiting_local_approval"
  | "executing_local_action" | "uploading" | "preparing_dispatch"
  | "sending_chat" | "starting_general_mission" | "failed";

export interface ConversationIntentState {
  phase: IntentRoutingPhase;
  requestEpoch: number;
  idempotencyKey: string;
  route: IntentRouteResponse | null;
  uploadAuthorization: string | null;
}
```

Generate 32-byte unpadded base64url keys with Web Crypto. Keep upload token only in memory and erase at terminal state. `Nouvelle conversation` first calls the provisional endpoint and disables its composer until success; two requests get distinct handles. Clarification is a panel above the composer, not a message. `IntentPreflightDialog` is general-mission only and may render vault workspace/tools/executor/cloud preview. A local route is passed only to the prior UI plan's `LocalAliasActionPanel`; its view has no model/executor/mission/writer/browser field and all callbacks call the dedicated local APIs. Access prepare/execute occurs only after `onVerifyAccess`; local finalization creates no writer admission; approval/execute uses the central typed local receipt without `missionId`.

For exact chat, the same Enter/`Continuer` gesture calls route, finalization, then the separate admission CAS without another click. General-mission confirmation performs finalization then the same explicit request may attempt admission. Capacity refusal keeps the already-created resource, route decision, draft, and file in `WAITING_FOR_WRITER`; a freed slot never triggers admission without `Réessayer`. Local alias action never calls admission, ChatGPT, extension or generic executor regardless of writer capacity.

- [ ] **Step 4: Re-run frontend tests to prove GREEN**

Run the command from Step 2.
Expected: all selected tests `PASS`; every input-matrix row uses exactly its documented endpoint path and no classifier-only state calls chat/mission/effect APIs.

- [ ] **Step 5: Commit the core frontend router**

```bash
git add frontend/lib/intent.ts frontend/lib/localAliasAction.ts frontend/hooks/useIntentRouter.ts frontend/workers/attachmentDigest.worker.ts frontend/components/IntentClarificationPanel.tsx frontend/components/IntentNoticePanel.tsx frontend/components/IntentPreflightDialog.tsx frontend/components/LocalAliasActionPanel.tsx frontend/lib/api.ts frontend/lib/types.ts frontend/lib/conversation-state.ts frontend/components/Composer.tsx frontend/components/ChatWorkspace.tsx frontend/components/CortexApp.tsx frontend/hooks/useIntentRouter.test.tsx frontend/components/IntentPreflightDialog.test.tsx frontend/components/LocalAliasActionIntegration.test.tsx frontend/components/Composer.test.tsx frontend/components/CortexApp.integration.test.tsx
git commit -m "feat: route one composer per conversation"
```

### Task 16: Render upload, writer, dispatch, consent, enrollment, STOP, and reconciliation rare states

**Files:**
- Create: `frontend/components/IntentActionStatus.tsx`
- Create: `frontend/components/DeliveryReconciliationPanel.tsx`
- Create: `frontend/components/LegacyReconciliationPanel.tsx`
- Create: `frontend/components/StopResetDialog.tsx`
- Modify: `frontend/hooks/useIntentRouter.ts`
- Modify: `frontend/components/CortexApp.tsx`
- Modify: `frontend/components/ChatWorkspace.tsx`
- Modify: `frontend/components/SettingsPanel.tsx`
- Modify: `frontend/components/PipelineInspector.tsx`
- Create: `frontend/components/IntentRareStates.test.tsx`
- Create: `frontend/components/DeliveryReconciliationPanel.test.tsx`
- Create: `frontend/components/StopResetDialog.test.tsx`

**Interfaces:**
- Consumes: Tasks 8-14 authoritative chat/general-mission/local-action, upload, dispatch, reconciliation, enrollment, consent and STOP responses, plus the UI plan's existing `LocalAliasActionPanel` state renderer.
- Produces: focused/keyboard-accessible renderers for non-local rare states and integration wiring for every local action result; it does not create a second local-action presenter or automatic retry.

- [ ] **Step 1: Write failing rare-state contract tests**

```tsx
it.each(["CHAT", "CONTRACT", "ITERATION_REPORT", "FOLLOW_UP"])(
  "renders %s uncertainty with exact preview and no automatic outbox", async (kind) => {
    render(<DeliveryReconciliationPanel message={uncertainMessage(kind)} />);
    expect(screen.getByRole("heading")).toHaveFocus();
    expect(screen.getByText(exactCopyFor(kind))).toBeVisible();
    expect(screen.getByText(immutablePreviewFor(kind))).toBeVisible();
    expect(api.outboxCreates).toBe(0);
  },
);

it("reset STOP requires one explicit gesture and resumes nothing", async () => {
  const sessionToken = uiSessionToken();
  const challenge = preparedStopResetChallenge(stoppedStatus());
  render(<StopResetDialog status={stoppedStatus()} sessionToken={sessionToken} challenge={challenge} />);
  await user.click(screen.getByRole("button", { name: "Réactiver les actions" }));
  expect(resetRequests).toEqual([{
    headers: { "X-Cortex-UI-Session": sessionToken },
    body: {
      resetAttemptId: expect.stringMatching(UUID_V4),
      expectedStateVersion: challenge.expectedStateVersion,
      expectedAuthorizationEpoch: challenge.expectedAuthorizationEpoch,
      nonce: challenge.nonce,
    },
  }]);
  expect(screen.getByText("L'arrêt global est désactivé. Aucune action n'a repris.")).toBeVisible();
  expect(resumedResources).toEqual([]);
});
```

Create an explicit matrix fixture for every French copy/action in Rare-state user flows and Accessibility/copy: waiting/expiry/cancel, four preparing copies and 150 ms threshold, upload reserve/stream/interruption/expiry/change/token loss, provisional failure, destination collision, four delivery kinds and replacements, account/conversation/surface/work errors, enrollment reconnect/read-only/missing/expired/key loss, consent absent/withdrawn before/after dispatch, STOP cancel/success/stale/concurrent, local alias permission/changed/existing/stale/cancelled/created/outcome-unclear results through the existing panel, migration failure, legacy keep/two-step delete/changed/unclear/four inspection results, prewarm stop, unsupported deletion, and routing-disabled explanation.

- [ ] **Step 2: Run rare-state tests to prove RED**

Run:
```bash
npm --prefix frontend run test:unit -- components/IntentRareStates.test.tsx components/DeliveryReconciliationPanel.test.tsx components/StopResetDialog.test.tsx
```
Expected: `FAIL` because authoritative rare-state components and exact recovery actions do not exist.

- [ ] **Step 3: Implement state-specific views with focus and no hidden authority**

Each view receives a discriminated server response and exposes only the permitted actions. Preserve draft/file on every pre-terminal failure. Abort upload plus authoritative cancel on edit/file/switch after reserve. Recover lost FSYNCED responses via status without reupload; any non-FSYNCED interruption requires a new route. At DISPATCHING remove cancel and all no-send promises. A successful consent grant, enrollment, STOP reset, reconciliation, or rebind never resumes automatically; the next action is explicit and receives fresh route/proof/key/fences as specified.

- [ ] **Step 4: Re-run rare-state unit tests**

Run:
```bash
npm --prefix frontend run test:unit -- components/IntentRareStates.test.tsx components/DeliveryReconciliationPanel.test.tsx components/StopResetDialog.test.tsx
```
Expected: unit tests `PASS`; each fixture proves focus return, Escape behavior, explicit accessible names, and unchanged information under reduced motion. Task 17 performs the 375/768/1440 browser viewport gate.

- [ ] **Step 5: Commit rare-state UX**

```bash
git add frontend/components/IntentActionStatus.tsx frontend/components/DeliveryReconciliationPanel.tsx frontend/components/LegacyReconciliationPanel.tsx frontend/components/StopResetDialog.tsx frontend/hooks/useIntentRouter.ts frontend/components/CortexApp.tsx frontend/components/ChatWorkspace.tsx frontend/components/SettingsPanel.tsx frontend/components/PipelineInspector.tsx frontend/components/IntentRareStates.test.tsx frontend/components/DeliveryReconciliationPanel.test.tsx frontend/components/StopResetDialog.test.tsx
git commit -m "feat: expose authoritative intent recovery states"
```

### Task 17: Prove extension dispatch and isolated local-alias action routing end to end

**Files:**
- Create: `frontend/e2e/hybrid-intent-router.spec.ts`
- Modify: `frontend/e2e/fixtures/app.ts`
- Modify: `chrome-extension/tests/extension.test.mjs`
- Modify: `tests/test_chrome_extension_readiness_regression.py`
- Modify: `tests/test_transport_session_isolation.py`

**Interfaces:**
- Consumes: all Tasks 1-16 interfaces and development-only deterministic fixture controls.
- Produces: tagged browser scenarios `@intent-route`, `@intent-upload`, `@intent-dispatch`, `@intent-safety`, `@intent-accessibility`, and `@intent-local-alias`.

- [ ] **Step 1: Write failing zero-side-effect and complete-decision E2E**

```ts
test("@intent-route obvious local request opens one complete preflight and sends nothing", async ({ page }) => {
  await submitExactDraft(page, "cree moi un dossier cortex-live-test sur mon bureau");
  const dialog = page.getByRole("dialog", { name: "Action locale" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Créer le dossier « cortex-live-test » dans Bureau.");
  await expect(dialog).toContainText("ChatGPT : aucun message envoyé");
  expect(await recordedEffects(page)).toEqual({
    chat: 0, upload: 0, mission: 0, writer: 0, outbox: 0,
    browser: 0, extension: 0, approval: 0, genericTool: 0, localWorker: 0,
  });
});

test("@intent-local-alias access and create stay outside every ChatGPT surface", async ({ page }) => {
  await submitExactDraft(page, "cree moi un dossier cortex-live-test sur mon bureau");
  await page.getByRole("button", { name: "Vérifier l’accès à Bureau" }).click();
  await expect(page.getByText("Accès vérifié")).toBeVisible();
  await page.getByRole("button", { name: "Continuer" }).click();
  await approveLocalAliasAction(page);
  await expect(page.getByRole("status")).toHaveText("Dossier créé");
  expect(await recordedEffects(page)).toMatchObject({
    localAccess: 1, localCreate: 1, mission: 0, writer: 0, outbox: 0,
    chat: 0, browser: 0, extension: 0, genericTool: 0,
  });
});
```

Add scenarios for obvious exact chat, vault `GeneralMission`, ambiguity/clarification, Ollama disabled/not-loaded/50 ms/151 ms/2 s, every input row, file invalidation/upload cuts/FSYNCED/token loss, two provisional/rekey/lost receipt/collision, two writers/third wait, PREPARING failpoints/cancel/retry/double retry, proof/account/surface/extension failures, both STOP/consent orders, STOP reset keyboard, every delivery kind and legacy reconciliation. Local-alias fixtures cover verification-required→explicit access, fake TCC hold/timeout, storage-not-ready, access expiry/revision, exact approval, existing target, STOP before activation, created inode, uncertain no-retry, two active writers unaffected, zero mission/outbox/browser/extension/generic tool, and no console/hydration/overflow error.

- [ ] **Step 2: Run tagged tests to prove RED**

Run:
```bash
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @intent-route
node --test chrome-extension/tests/extension.test.mjs
```
Expected: `FAIL`; the new E2E scenarios and final extension identity/ledger assertions are not all implemented.

- [ ] **Step 3: Complete fixture barriers and deterministic clocks**

Fixtures expose only development-gated local barriers, fake clocks, fake Ollama, disposable SQLite/upload/quarantine/workspace roots, and recorded calls. They never expose a production fault endpoint, never reuse a live Chrome profile, and never accept absolute personal paths. Assert every selected tag runs at least one test.

- [ ] **Step 4: Run all tagged E2E and extension/backend integration tests**

Run:
```bash
npm --prefix frontend run test:e2e -- --grep @intent-route
npm --prefix frontend run test:e2e -- --grep @intent-upload
npm --prefix frontend run test:e2e -- --grep @intent-dispatch
npm --prefix frontend run test:e2e -- --grep @intent-safety
npm --prefix frontend run test:e2e -- --grep @intent-accessibility
npm --prefix frontend run test:e2e -- --grep @intent-local-alias
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_readiness_regression.py
"$PYTHON" tests/test_transport_session_isolation.py
```
Expected: every command exits zero, every tag selects tests, and no browser fixture reports an unclassified effect, duplicate resource, automatic retry, or skipped integration.

- [ ] **Step 5: Commit end-to-end coverage**

```bash
git add frontend/e2e/hybrid-intent-router.spec.ts frontend/e2e/fixtures/app.ts chrome-extension/tests/extension.test.mjs tests/test_chrome_extension_readiness_regression.py tests/test_transport_session_isolation.py
git commit -m "test: prove hybrid intent routing end to end"
```

### Task 18: Package, document, and run the complete release-candidate gates

**Files:**
- Modify: `pyproject.toml:20-47`
- Modify: `docs/routing-policy.md`
- Modify: `docs/interface.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/v0.5.0-design.md`
- Modify: `frontend/components/BridgeDiagram.tsx`
- Modify: `frontend/lib/bridge-diagram-model.ts`
- Modify: `scripts/test-all.sh`
- Create: `tests/test_installed_intent_wheel.py`
- Modify: `tests/test_verify_runtime.py`
- Run without modification: `tests/test_installer.py`, `tests/test_local_alias_worker.py`, `tests/test_local_alias_worker_runner.py`, `tests/test_effect_gate.py`, `tests/test_store_lifecycle.py`

**Interfaces:**
- Consumes: every task contract; exact configured Cortex frontend origins; product port `127.0.0.1:8420`.
- Produces: installed-wheel intent imports, durable schema-v3/worker conformance, exact CORS smoke, English public docs, French UI copy and aggregate no-skip gate.

- [ ] **Step 1: Write failing installed-wheel and CORS smoke tests**

```python
class InstalledIntentWheelTest(unittest.TestCase):
    def test_installed_wheel_imports_router_and_consumes_attested_local_worker(self):
        result = self.installed_env.run("intent-smoke")
        self.assertTrue(result.router_imported)
        self.assertEqual(result.migration_version, 3)
        self.assertTrue(result.local_alias_action_service_imported)
        self.assertTrue(result.local_alias_worker_attested)
        self.assertEqual(result.generic_executor_local_alias_edges, 0)

    def test_exact_origin_cors_accepts_only_required_intent_headers(self):
        for method, header in (
            ("POST", "Idempotency-Key"),
            ("POST", "X-Cortex-UI-Session"),
            ("PUT", "X-Cortex-Upload-Authorization"),
        ):
            with self.subTest(method=method, header=header):
                accepted = self.cors_client.preflight(
                    origin=CONFIGURED_ORIGIN, method=method, header=header,
                )
                rejected = self.cors_client.preflight(
                    origin="http://evil.invalid", method=method, header=header,
                )
                self.assertEqual(accepted.status_code, 200)
                self.assertNotEqual(rejected.status_code, 200)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() == 0:
        raise SystemExit("ZERO_TESTS_SELECTED")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
```

Cover `GET/POST/PUT/DELETE/OPTIONS`, `Content-Type`, `Last-Event-ID`, the three new headers, local access prepare/execute and local approval POSTs, every other origin/method/header, JSON body limits, raw octet-stream, application authentication independent of CORS, unavailable durable worker hiding local finalization, and package imports for all new `py-modules`.

- [ ] **Step 2: Run smoke tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_installed_intent_wheel.py
"$PYTHON" tests/test_installer.py
"$PYTHON" tests/test_verify_runtime.py
scripts/verify-links.sh
```
Expected: `FAIL`; packaging, installed smoke, docs links, and exact CORS allowlist are incomplete.

- [ ] **Step 3: Finish packaging, documentation, and aggregate runner**

Add only new intent modules `intent_router`, `intent_models`, `intent_rules`, `intent_classifier`, `intent_routes`, `intent_store`, `workspace_catalog`, and `local_alias_actions` to explicit packaging; consume the already packaged durable worker/runner without adding an executor module. Document the one-composer route matrix, formal GeneralMission/LocalAliasAction split, local-only classifier, vault-only workspace authority, access/TCC boundary, central approval, uploads, writer waiting, uncertainty/reconciliation, extension enrollment and STOP reset. Add supersession notes referencing the addendum hash without rewriting history. Add every new intent/frontend/build/E2E/accessibility/runtime/privacy/installed-wheel test to `scripts/test-all.sh`; run durable worker/effect/schema tests unchanged with zero-test/skip rejection.

- [ ] **Step 4: Run complete automated and static gates**

Run:
```bash
test -d frontend/node_modules
PYTHON="$PYTHON" scripts/test-all.sh
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
scripts/verify-links.sh
git diff --check
git status --short
```
Expected: Python 3.11 and 3.14 backend matrices, extension suite, frontend unit/contracts/typecheck/lint/fresh build/E2E/accessibility/runtime/privacy, installed-wheel smoke, links, both Gitleaks scans, and diff check all exit zero with no required skip; Git lists only reviewed source/test/doc changes and no generated evidence.

- [ ] **Step 5: Commit packaging and documentation**

```bash
git add pyproject.toml docs/routing-policy.md docs/interface.md docs/user-guide.md docs/v0.5.0-design.md frontend/components/BridgeDiagram.tsx frontend/lib/bridge-diagram-model.ts scripts/test-all.sh tests/test_installed_intent_wheel.py tests/test_verify_runtime.py
git commit -m "docs: ship hybrid intent routing contracts"
```

## Live Acceptance Boundary

- The owner acceptance fixture is separate from implementation and automated tests. It requires action-time approval before any real ChatGPT message, browser mutation, local write, or extension restart.
- Before the acceptance request, prove healthy managed required storage, explicitly click `Vérifier l’accès à Bureau`, let the owner alone decide any macOS prompt, and require one fresh observation with zero ChatGPT/mission/writer/outbox/browser/extension effect.
- Prove by `lstat` that `Desktop/cortex-live-test` is absent; if it exists, record `UNCLEAR` and do not delete or rename it.
- The exact typed draft is `cree moi un dossier cortex-live-test sur mon bureau`. PASS requires `source=rules`, `model_attempted=false`, `model_used=null`, `executionClass=local_alias_action`, exact French Action locale interpretation, target absent through routing/finalization, one central action/digest/nonce/epoch-bound approval, one new inode/terminal receipt afterward, no unrelated Desktop entry change, and zero ChatGPT, mission, writer, outbox, browser, extension or generic executor activity.
- Any missing approval, inode observation, destination identity, visible transport evidence, or unrelated-workspace inventory yields `UNCLEAR`; any premature/duplicate/wrong effect yields `FAIL`.
- Live owner acceptance does not authorize merge, tag, push, release, arbitrary network, process execution, deletion, or any broader local change.
