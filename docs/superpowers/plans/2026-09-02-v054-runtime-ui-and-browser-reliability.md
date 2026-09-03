# v0.5.4 Runtime UI and Browser Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make runtime/workspace/local-action truth, local-alias access and outcome states, conversation switching, tab ownership, sidebar navigation, and diagnostic export truthful and bounded in the v0.5.4 product UI.

**Architecture:** Pure observation producers feed one versioned runtime composer, and all four backend endpoints return explicit projections of the same composed value. Local-action readiness is a separate projection of storage/managed-runtime/effect-gate facts and its frontend view receives no model or executor field; conversation refresh uses cache-first state with independent 8-second transport and 10-second UI deadlines, while the extension keeps fail-closed in-memory tab provenance. Each repair is regression-tested before implementation and remains separate from storage lifecycle, durable worker/effect ownership, and intent routing/finalization.

**Tech Stack:** Python 3.11/3.14, FastAPI/Pydantic, TypeScript, React 19, Vitest/Testing Library, Playwright, Chrome MV3 JavaScript, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` (approved SHA-256 `2034280b1b4943c2b602eba888b58742e2d77b428bdc63dc5f93a4b59c72cb5f`) plus normative `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` (approved SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`)

## Global Constraints

- Consume `StorageContract(home).probe() -> StorageStatus`, `.assert_runtime_ready() -> StorageStatus`, `.open() -> StorageBinding`, `.revalidate(binding) -> MountFacts`, and `.open_workspace(binding, requested) -> WorkspaceHandle` from the storage-foundation plan; do not modify `console/storage_contract.py` or recreate mount, path, FD, APFS, UUID, ownership, journal, or mission-admission checks here.
- Consume `WorkspaceHandle.identity`, `.mount_fd`, `.workspace_fd`, `.display_path`, `.revalidate()`, `.duplicate_workspace_fd()`, and `.close()` without modifying `executor/workspace_handle.py`.
- Consume `EffectGate.status/register_pending_approval/decide_approval/activate_mission_effect/begin_direct_intent/activate_direct_intent/assert_activation/record_ownership/succeed/fail/outcome_unclear/request_stop/settle_stop/reset_stop/reconcile_startup` and its permits from the durable-effects plan; do not modify `console/effect_gate.py` or `orchestration/store.py`, and do not recreate STOP serialization, effect persistence, approval consumption, or reconciliation here.
- `console/runtime_observations.py` imports no FastAPI route module; `console/runtime_truth.py` is the sole runtime composer.
- `iterations.json` and `_latest_local_task_runtime_truth` are historical only and must never influence current executor, workspace, readiness, or release eligibility.
- `/api/status`, `/api/pipeline/status`, `/api/settings`, and `/api/onboarding` must project one `schema_version=1` truth assembled from current observations.
- `executor_available=true` never overrides `executor_kind=unavailable`, a failed component, `release_eligible=false`, or an unusable workspace.
- `local_alias_action` is not a mission. Its runtime readiness comes only from `StorageContract.assert_runtime_ready()`, managed-runtime truth, and `EffectGate.status()`; it is independent of Ollama/model/executor availability and never receives a `WorkspaceHandle`.
- The local-action frontend types and component props contain no model or executor field. They expose only fixed alias metadata, access/action state, storage/runtime readiness, approval facts, and bounded error codes.
- Only an explicit click on `Vérifier l’accès à Bureau|Documents|Téléchargements` may call the future intent-owned two-step access API. This UI never opens an alias, controls a macOS TCC prompt, starts a worker, or fabricates an access observation.
- Render the exact class label `Action locale`, `ChatGPT : aucun message envoyé`, disabled read/deletion/process/network capabilities, and terminal states `Création en cours…`, `Dossier créé`, or `Résultat incertain — ne relancez pas automatiquement` according to authoritative records only.
- Consume the intent plan's future camelCase local-alias route/action envelopes through typed callbacks and fixtures; do not implement routing, finalization, catalog, observation, grant, action persistence, filesystem work, or effect activation in this plan.
- Under required storage or release runtime, `browser_transport` is exactly `chrome_extension`; `playwright` and `webbridge` remain explicit development fixtures only and are absent from product Settings controls.
- Conversation selection renders the last verified cache immediately, gives transport acquisition 8,000 ms, settles the UI within 10,000 ms, and prevents an aborted or superseded request from committing.
- A tab may be retired only when `origin=cortex`, `role=read_only`, its session and canonical conversation match the owned writer, and `in_flight_commands=0`; missing provenance is user-owned.
- Service-worker restart, tab-ID reuse, `tabs.onRemoved`, delivery uncertainty, or two live writers must fail closed without closing or repurposing a user tab.
- Remove the archives control because no backend archive contract exists; preserve pinned, project, recent, and new-conversation controls.
- Diagnostic export may claim only `Téléchargement demandé`, names the generated file, creates one DOM-attached link, clicks once, removes it, then revokes the Blob URL after deferred cleanup.
- Static runtime values are allowed only behind `NEXT_PUBLIC_CORTEX_DEVELOPMENT_FIXTURES=1`.
- Do not run Chrome, a server, a live runtime, storage cutover, browser pairing, or external send while executing this plan; no merge, tag, push, release claim, or generated QA evidence is authorized.
- Every required command that selects zero tests, skips a required integration, or lacks the expected trace/download is `FAIL`.
- Python tests import stdlib `sys` and `unittest` and use no third-party test runner: synchronous cases live in `unittest.TestCase`, async cases in `unittest.IsolatedAsyncioTestCase`, matrices use `self.subTest`, and every newly created directly executed test module loads its suite, rejects `countTestCases() == 0`, runs it with `unittest.TextTestRunner(verbosity=2)`, and exits nonzero unless `wasSuccessful()`.

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

- Create `console/runtime_observations.py`: pure current storage/workspace/executor/pipeline observation producers.
- Create `console/runtime_truth.py`: Pydantic v1 response contract, invariant validation, and four endpoint projections.
- Modify `console/server.py`, `console/settings.py`, `console/onboarding.py`: remove independent inference and expose projections from the shared composer.
- Modify `frontend/lib/types.ts`, `frontend/lib/runtimeTruth.ts`, `frontend/components/CortexApp.tsx`, `frontend/components/SettingsPanel.tsx`, `frontend/components/OnboardingPanel.tsx`, `frontend/components/StatusRail.tsx`: consume the shared truth without hardcoded product health.
- Create `frontend/lib/localAliasAction.ts` and `frontend/components/LocalAliasActionPanel.tsx`: render the intent-owned local-action envelope and expose only explicit user callbacks for access verification/finalization.
- Modify `frontend/components/ChatWorkspace.tsx`: host the local-action panel without turning it into a mission or ChatGPT message.
- Modify `transport/chatgpt_web/adapter.py`, `console/chat.py`, `frontend/hooks/useConversationController.ts`, `frontend/lib/conversation-state.ts`: cache-first switch with two bounded deadlines and epoch fencing.
- Create `transport/chatgpt_web/snapshot_fault.py`: development-only one-shot refresh timeout transport.
- Modify `chrome-extension/service-worker-core.js`, `chrome-extension/service-worker.js`: in-memory provenance registry and conservative redundant-reader retirement.
- Modify `frontend/components/ConversationSidebar.tsx`: remove unsupported archives action only.
- Create `frontend/components/SettingsPanel.diagnostic-export.test.tsx` and `frontend/e2e/runtime-browser-reliability.spec.ts`: focused diagnostic and runtime/browser acceptance.

### Task 1: Compose one authoritative backend runtime truth

**Files:**
- Create: `console/runtime_observations.py`
- Create: `console/runtime_truth.py`
- Modify: `console/server.py:35-85,243-245`
- Modify: `console/settings.py:21-38,304-739`
- Modify: `console/onboarding.py:268-375`
- Test: `tests/test_executor_runtime_truth.py`
- Create: `tests/test_onboarding_runtime_truth.py`
- Test: `tests/test_chat_settings_api.py`

**Interfaces:**
- Consumes: `StorageContract(home).probe() -> StorageStatus` for storage truth, `StorageContract.assert_runtime_ready() -> StorageStatus` for local-action admission readiness, `StorageContract.open_workspace(binding, requested) -> WorkspaceHandle` for general-mission workspace validation, and `EffectGate.status() -> StopStatus`; mission rows from `missions.get_store()` are historical/current data, not authority by themselves.
- Produces: `collect_runtime_observations(*, storage_contract: StorageContract, effect_gate: EffectGate, settings: Mapping[str, object], mission_id: str | None, conversation_identity: str | None) -> RuntimeObservations`; `compose_runtime_truth(observations: RuntimeObservations) -> RuntimeTruthV1`; `LocalActionRuntimeTruth`; `RuntimeTruthV1.for_status()`, `.for_pipeline(scope)`, `.for_settings(settings)`, and `.for_onboarding(completed)`.

- [ ] **Step 1: Write the failing backend contract tests**

```python
class RuntimeTruthEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def test_four_endpoints_project_the_same_current_truth(self):
        self.runtime_facts(storage_ready=False, workspace_usable=False,
                           executor_available=True, executor_kind="unavailable")
        status = (await self.client.get("/api/status")).json()
        pipeline = (await self.client.get("/api/pipeline/status")).json()
        settings = (await self.client.get("/api/settings")).json()
        onboarding = (await self.client.get("/api/onboarding")).json()
        self.assertEqual(
            {status["runtime_truth_digest"], pipeline["runtime_truth_digest"],
             settings["runtime_truth_digest"], onboarding["runtime_truth_digest"]},
            {status["runtime_truth_digest"]},
        )
        self.assertFalse(status["runtime_truth"]["ready"])
        self.assertEqual(pipeline["runtime_truth"]["executor"]["kind"], "unavailable")
        self.assertFalse(settings["runtime_truth"]["workspace"]["usable"])
        self.assertFalse(onboarding["ready"])

    async def test_contradictory_iterations_history_cannot_become_current_truth(self):
        self.iterations_file.write_text(
            '[{"status":"running","executor_kind":"ollama",'
            '"release_eligible":true}]', encoding="utf-8",
        )
        for path in ("/api/status", "/api/pipeline/status", "/api/settings", "/api/onboarding"):
            with self.subTest(path=path):
                truth = (await self.client.get(path)).json()["runtime_truth"]
                self.assertEqual(truth["executor"]["kind"], "unavailable")
                self.assertFalse(truth["release_eligible"])

    async def test_local_action_readiness_ignores_model_and_executor_but_not_storage_or_stop(self):
        self.runtime_facts(storage_runtime_ready=True, managed_runtime=True,
                           stop_accepting_effects=True, executor_kind="unavailable")
        truth = (await self.client.get("/api/status")).json()["runtime_truth"]
        self.assertEqual(truth["local_action"], {
            "ready": True, "storage_ready": True, "managed_runtime": True,
            "accepting_effects": True, "code": "LOCAL_ACTION_READY",
        })
        self.runtime_facts(storage_runtime_ready=False, managed_runtime=True,
                           stop_accepting_effects=True, executor_kind="ollama")
        blocked = (await self.client.get("/api/status")).json()["runtime_truth"]["local_action"]
        self.assertFalse(blocked["ready"])
        self.assertEqual(blocked["code"], "STORAGE_NOT_READY")
```

Place these methods in the existing temporary-runtime API harnesses; the new `tests/test_onboarding_runtime_truth.py` defines the same `asyncSetUp`/cleanup pattern and ends with the mandated nonzero suite runner.

- [ ] **Step 2: Run the focused tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_executor_runtime_truth.py
"$PYTHON" tests/test_onboarding_runtime_truth.py
"$PYTHON" tests/test_chat_settings_api.py
```
Expected: `FAIL` because the shared `runtime_truth`/digest projections do not exist and global pipeline still reads `_latest_local_task_runtime_truth()`.

- [ ] **Step 3: Add pure observations and the sole composer**

```python
@dataclass(frozen=True, slots=True)
class RuntimeObservations:
    observed_at: str
    storage: StorageObservation
    workspace: WorkspaceObservation
    executor: ExecutorObservation
    local_action: LocalActionRuntimeObservation
    pipeline: tuple[PipelineComponentObservation, ...]

class LocalActionRuntimeTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ready: bool
    storage_ready: bool
    managed_runtime: bool
    accepting_effects: bool
    code: Literal["LOCAL_ACTION_READY", "STORAGE_NOT_READY", "RUNTIME_NOT_MANAGED", "STOP_ACTIVE"]

class RuntimeTruthV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    observed_at: str
    storage: StorageTruth
    workspace: WorkspaceTruth
    executor: ExecutorTruth
    local_action: LocalActionRuntimeTruth
    pipeline: tuple[PipelineComponentTruth, ...]
    ready: bool
    release_eligible: bool
    digest: str

def compose_runtime_truth(observations: RuntimeObservations) -> RuntimeTruthV1:
    ready = (
        observations.storage.ready
        and observations.workspace.usable
        and observations.executor.kind != "unavailable"
        and all(row.state not in {"failed", "unavailable"} for row in observations.pipeline)
    )
    release_eligible = ready and observations.executor.release_eligible
    return RuntimeTruthV1.from_observations(observations, ready, release_eligible)
```

Compose `local_action.ready = storage_status.runtime_allowed and managed_runtime and stop_status.accepting_effects` with the stable blocker precedence `STORAGE_NOT_READY`, `RUNTIME_NOT_MANAGED`, then `STOP_ACTIVE`; never consult executor/model/workspace facts for that field. Route handlers call one request-scoped `runtime_truth_snapshot(storage_contract: StorageContract, effect_gate: EffectGate, settings: Mapping[str, object], mission_id: str | None, conversation_identity: str | None) -> RuntimeTruthV1` dependency and return only its explicit projection. Delete `_latest_local_task_runtime_truth()` and the `TASK_STORE_FILE` read from `console/settings.py`; keep `iterations.json` retrieval only on the read-only historical task surface.

- [ ] **Step 4: Re-run the focused tests to prove GREEN**

Run the three commands from Step 2.
Expected: all selected tests `PASS`; all four responses carry `schema_version=1`, one identical digest for one frozen observation fixture, and no current-truth code reads `iterations.json`.

- [ ] **Step 5: Commit this isolated change**

```bash
git add console/runtime_observations.py console/runtime_truth.py console/server.py console/settings.py console/onboarding.py tests/test_executor_runtime_truth.py tests/test_onboarding_runtime_truth.py tests/test_chat_settings_api.py
git commit -m "fix: unify runtime and workspace truth"
```

### Task 2: Make CortexApp, Settings, Onboarding, and the status rail render the same truth

**Files:**
- Modify: `frontend/lib/types.ts:152-184,276-313,371-393`
- Modify: `frontend/lib/runtimeTruth.ts:74-199,290-365`
- Modify: `frontend/components/CortexApp.tsx:251-760,1130-1285`
- Modify: `frontend/components/SettingsPanel.tsx:1-38,255-330`
- Modify: `frontend/components/OnboardingPanel.tsx:8-165`
- Modify: `frontend/components/StatusRail.tsx:1-38`
- Test: `frontend/components/CortexApp.integration.test.tsx`
- Create: `frontend/components/OnboardingPanel.test.tsx`
- Test: `frontend/components/SettingsPanel.regression-1.test.tsx`
- Test: `frontend/components/StatusRail.test.tsx`
- Test: `frontend/lib/runtimeTruth.test.mts`

**Interfaces:**
- Consumes: `RuntimeTruthV1` JSON from Task 1 on all four endpoints.
- Produces: `RuntimeTruthV1`, `RuntimeEndpointEnvelope<T>`, `runtimeReadiness(truth)`, `componentPresentation(component)`, and panel props that carry the same `runtimeTruth` object.

- [ ] **Step 1: Write the failing frontend truth tests**

```tsx
it("shows an unavailable executor and workspace in every product panel", async () => {
  installRuntimeTruth({ executor: { kind: "unavailable", available: true }, workspace: { exists: false, usable: false }, ready: false });
  render(<CortexApp />);
  expect(await screen.findByText("Exécuteur indisponible")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Paramètres" }));
  expect(screen.queryByText("healthy")).not.toBeInTheDocument();
  expect(screen.queryByText("ready")).not.toBeInTheDocument();
  expect(screen.getByText("Workspace indisponible")).toBeVisible();
  expect(screen.getByRole("dialog", { name: /Bienvenue|Guide de démarrage/ }))
    .toHaveTextContent("Workspace indisponible");
});

it("does not turn executor_available into observed execution truth", () => {
  expect(runtimeReadiness(runtimeTruth({ executor: { available: true, kind: "unavailable" } })))
    .toEqual({ ready: false, executorState: "unavailable" });
});
```

- [ ] **Step 2: Run the focused unit tests to prove RED**

Run:
```bash
npm --prefix frontend run test:unit -- components/CortexApp.integration.test.tsx components/OnboardingPanel.test.tsx components/SettingsPanel.regression-1.test.tsx components/StatusRail.test.tsx lib/runtimeTruth.test.mts
```
Expected: `FAIL` because `CortexApp` derives the agent pill from `runtime.executor_available`, Settings hardcodes `healthy`/`ready`/demo paths, and Onboarding owns a separate check schema.

- [ ] **Step 3: Replace frontend inference with typed projections**

```ts
export interface RuntimeTruthV1 {
  schema_version: 1;
  digest: string;
  ready: boolean;
  release_eligible: boolean;
  storage: { state: HealthState; ready: boolean; detail: string };
  workspace: { exists: boolean; usable: boolean; label: string; display_path: string | null; reason: string | null };
  executor: { available: boolean; kind: ExecutorKind; model_used: string | null; release_eligible: boolean; state: HealthState };
  local_action: LocalActionRuntimeTruth;
  pipeline: PipelineComponent[];
}

export interface LocalActionRuntimeTruth {
  ready: boolean;
  storage_ready: boolean;
  managed_runtime: boolean;
  accepting_effects: boolean;
  code: "LOCAL_ACTION_READY" | "STORAGE_NOT_READY" | "RUNTIME_NOT_MANAGED" | "STOP_ACTIVE";
}

export function runtimeReadiness(truth: RuntimeTruthV1) {
  return {
    ready: truth.ready,
    executorState: truth.executor.kind === "unavailable" ? "unavailable" : truth.executor.state,
  } as const;
}
```

Pass the same current `runtimeTruth` from `CortexApp` to `StatusRail`, `SettingsPanel`, and `OnboardingPanel`. Remove product literals `healthy`, `ready`, `/tmp/cortex-demo-workspace/models`, `console/data/cortex.db`, and `WebBridge experimental`; render backend labels/details or a typed unavailable value. Keep demo values only in `frontend/lib/demo.ts` behind the existing fixture flag.

- [ ] **Step 4: Re-run the focused tests and runtime contracts**

Run:
```bash
npm --prefix frontend run test:unit -- components/CortexApp.integration.test.tsx components/OnboardingPanel.test.tsx components/SettingsPanel.regression-1.test.tsx components/StatusRail.test.tsx lib/runtimeTruth.test.mts
npm --prefix frontend run test:runtime
```
Expected: all selected unit and runtime-contract tests `PASS`; no product panel fabricates readiness or a path.

- [ ] **Step 5: Commit this isolated change**

```bash
git add frontend/lib/types.ts frontend/lib/runtimeTruth.ts frontend/components/CortexApp.tsx frontend/components/SettingsPanel.tsx frontend/components/OnboardingPanel.tsx frontend/components/StatusRail.tsx frontend/components/CortexApp.integration.test.tsx frontend/components/OnboardingPanel.test.tsx frontend/components/SettingsPanel.regression-1.test.tsx frontend/components/StatusRail.test.tsx frontend/lib/runtimeTruth.test.mts
git commit -m "fix: render shared runtime truth in every panel"
```

### Task 3: Lock product transport to the Chrome extension

**Files:**
- Modify: `frontend/components/SettingsPanel.tsx:255-287`
- Modify: `frontend/lib/types.ts:371-393`
- Test: `frontend/components/SettingsPanel.regression-1.test.tsx`
- Inspect for backend conformance only: `console/settings.py`, `transport/browser.py`
- Run without modification: `tests/test_chat_settings_api.py`, `tests/test_chrome_extension_driver.py`

**Interfaces:**
- Consumes unchanged: storage-foundation `validate_browser_transport(settings: Mapping[str, object], *, storage_status: StorageStatus, development_fixture: bool) -> Literal["chrome_extension", "playwright", "webbridge"]`, its committed three-field projection, and its factory clamp before driver construction.
- Produces only: frontend `BrowserTransport = "chrome_extension"` on the product Settings surface and a read-only `Extension Chrome` presentation; no backend validator, storage inference, or browser factory is added here.

- [ ] **Step 1: Add the failing frontend transport-presentation test**

```tsx
it("shows Chrome extension as fixed product transport", () => {
  renderSettings({ browser_transport: "chrome_extension" });
  expect(screen.getByText("Extension Chrome")).toBeVisible();
  expect(screen.queryByRole("combobox", { name: "Driver navigateur" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Playwright|WebBridge/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
npm --prefix frontend run test:unit -- components/SettingsPanel.regression-1.test.tsx
```
Expected: `FAIL` because Settings still renders a product transport selector and names Playwright/WebBridge. The backend clamp is already green from the storage-foundation plan and is not part of this RED.

- [ ] **Step 3: Render the storage-owned product transport without a selector**

```ts
export type BrowserTransport = "chrome_extension";

export function ProductBrowserTransportRow() {
  return <ReadonlySetting label="Driver navigateur" value="Extension Chrome" />;
}
```

Replace the product select with the read-only row and remove Playwright/WebBridge/profile-root product controls from `SettingsPanel`. The frontend sends no browser-transport mutation. Development-fixture controls remain outside the product Settings component and continue to depend on the existing explicit fixture gate.

- [ ] **Step 4: Prove frontend GREEN and backend conformance read-only**

Run:
```bash
npm --prefix frontend run test:unit -- components/SettingsPanel.regression-1.test.tsx
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" tests/test_chrome_extension_driver.py
```
Expected: all selected tests `PASS`; the frontend exposes only the fixed Chrome-extension row, while the unchanged storage-owned backend tests still prove legacy values yield zero driver construction under required storage.

- [ ] **Step 5: Commit this isolated change**

```bash
git add frontend/components/SettingsPanel.tsx frontend/lib/types.ts frontend/components/SettingsPanel.regression-1.test.tsx
git commit -m "fix(ui): render storage-owned browser transport clamp"
```

### Task 4: Render local-alias access, approval, creation, and uncertain states without executor/model authority

**Files:**
- Create: `frontend/lib/localAliasAction.ts`
- Create: `frontend/components/LocalAliasActionPanel.tsx`
- Create: `frontend/components/LocalAliasActionPanel.test.tsx`
- Modify: `frontend/components/ChatWorkspace.tsx:37-90,360-690`
- Modify: `frontend/components/ChatWorkspace.test.tsx`
- Modify: `frontend/e2e/fixtures/app.ts`
- Modify: `frontend/e2e/runtime-browser-reliability.spec.ts`

**Interfaces:**
- Consumes: Task 1 `LocalActionRuntimeTruth`; intent-addendum camelCase `LocalAliasActionView` supplied by the later intent plan; callbacks `onVerifyAccess(alias)`, `onFinalizeLocalAction(routeId)`, `onSendOnlyToChatGPT(routeId)`, and `onDismissLocalAction(routeId)`. It does not import mission, executor, model, writer, browser, or extension types.
- Produces: `LocalAliasActionPanel`; `localAliasPresentation(view) -> LocalAliasPresentation`; and `ChatWorkspace`'s optional `localAliasAction`/four callback props. No API call or authority is created inside the presentation helper.

- [ ] **Step 1: Write failing rendering, explicit-access, terminal-proof, and keyboard tests**

```tsx
it("labels the route as a local action and never implies ChatGPT or executor work", () => {
  renderLocalAliasPanel(verificationRequiredView());
  expect(screen.getByRole("heading", { name: "Action locale" })).toBeVisible();
  expect(screen.getByText("Créer le dossier « cortex-live-test » dans Bureau.")).toBeVisible();
  expect(screen.getByText("ChatGPT : aucun message envoyé")).toBeVisible();
  expect(screen.getByText("Lecture, suppression, processus et réseau : désactivés")).toBeVisible();
  expect(screen.queryByText(/Ollama|modèle|exécuteur/i)).not.toBeInTheDocument();
});

it("starts the alias access check only from the explicit keyboard-operable click", async () => {
  const onVerifyAccess = vi.fn();
  renderLocalAliasPanel(verificationRequiredView(), { onVerifyAccess });
  expect(onVerifyAccess).not.toHaveBeenCalled();
  expect(screen.getByText("macOS peut demander votre autorisation. Cortex ne peut pas la valider à votre place.")).toBeVisible();
  await user.tab();
  await user.keyboard("{Enter}");
  expect(onVerifyAccess).toHaveBeenCalledExactlyOnceWith("desktop");
});

it.each([
  ["verifying", "Vérification de l’accès…", "status"],
  ["active", "Création en cours…", "status"],
  ["created", "Dossier créé", "status"],
  ["outcome_unclear", "Résultat incertain — ne relancez pas automatiquement", "alert"],
] as const)("renders authoritative %s state", (state, copy, role) => {
  renderLocalAliasPanel(actionView({ state, createdInode: state === "created" ? 4242 : null,
                                     terminalReceipt: state === "created" ? receipt() : null }));
  expect(screen.getByRole(role)).toHaveTextContent(copy);
});
```

Also prove `created` without both terminal receipt and inode is rendered as `outcome_unclear`; permission-required, alias-changed, target-existing, STOP, stale-approval and denial copies are distinct; verification/finalization buttons are disabled when `localRuntime.ready=false`; finalization stays disabled without a fresh access observation; the pre-write warning says macOS may ask again after revocation; draft bytes survive every denial/failure/uncertain state; and the explicit `Envoyer seulement à ChatGPT` callback is the only chat escape.

- [ ] **Step 2: Run the focused frontend tests to prove RED**

Run:
```bash
npm --prefix frontend run test:unit -- components/LocalAliasActionPanel.test.tsx components/ChatWorkspace.test.tsx
```
Expected: `FAIL` because the local-action view types/component and `ChatWorkspace` branch do not exist.

- [ ] **Step 3: Implement the presentation-only discriminated contract**

```ts
export type LocalAlias = "desktop" | "documents" | "downloads";
export type LocalAliasAccessState =
  | "verification_required" | "verifying" | "verified"
  | "permission_required" | "access_unclear";
export type LocalAliasActionState =
  | "awaiting_approval" | "active" | "created" | "failed_safe"
  | "outcome_unclear" | "cancelled_by_stop";

export interface LocalAliasActionView {
  executionClass: "local_alias_action";
  routeId: string;
  alias: LocalAlias;
  label: "Bureau" | "Documents" | "Téléchargements";
  leaf: string;
  interpretation: string;
  accessState: LocalAliasAccessState;
  accessObservationId: string | null;
  actionState: LocalAliasActionState | null;
  createdInode: number | null;
  terminalReceipt: { effectId: string; code: string } | null;
  errorCode: string | null;
  localRuntime: LocalActionRuntimeTruth;
  requires: {
    writeApproval: true; chatgpt: false; writer: false; read: false;
    process: false; network: false; deletion: false;
  };
}

export function localAliasPresentation(view: LocalAliasActionView): LocalAliasPresentation { ... }
```

`localAliasPresentation` maps only the frozen access/action/error literals to the exact French copy. It downgrades a claimed `created` lacking both `createdInode` and `terminalReceipt` to the uncertain alert. `LocalAliasActionPanel` calls no fetch function, reads no runtime singleton, and receives no `executor`, `model`, mission, writer, browser or extension prop. `ChatWorkspace` renders it above the composer, retains the original draft until successful finalization, and never inserts verification/refusal/action state into the message list.

- [ ] **Step 4: Prove GREEN, fresh-build rendering, and bounded responsive accessibility**

Run:
```bash
npm --prefix frontend run test:unit -- components/LocalAliasActionPanel.test.tsx components/ChatWorkspace.test.tsx
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @local-alias-ui
```
Expected: unit/build gates `PASS`; the tagged fixture runs at 375, 768 and 1440 CSS pixels with no horizontal overflow, explicit access/finalize focus order, live-region state announcements, preserved draft, and zero chat/mission/browser fixture call before or after access-state rendering.

- [ ] **Step 5: Commit the local-action UI contract**

```bash
git add frontend/lib/localAliasAction.ts frontend/components/LocalAliasActionPanel.tsx frontend/components/LocalAliasActionPanel.test.tsx frontend/components/ChatWorkspace.tsx frontend/components/ChatWorkspace.test.tsx frontend/e2e/fixtures/app.ts frontend/e2e/runtime-browser-reliability.spec.ts
git commit -m "feat(ui): render local alias action states"
```

### Task 5: Implement cache-first conversation switching with bounded acquisition

**Files:**
- Modify: `transport/chatgpt_web/adapter.py:437-810,1118-1136`
- Modify: `console/chat.py:181-191,322-552`
- Modify: `frontend/hooks/useConversationController.ts:20-334`
- Modify: `frontend/lib/conversation-state.ts:27-340`
- Test: `tests/test_transport_fixture.py`
- Test: `tests/test_transport_session_isolation.py`
- Test: `frontend/hooks/useConversationController.test.tsx`

**Interfaces:**
- Consumes: existing `ConversationSnapshot`, `ConversationEntry`, `AbortSignal`, and read-only session isolation.
- Produces: `TRANSPORT_SNAPSHOT_BUDGET_SECONDS = 8.0`; `conversation_snapshot(..., cached: int = 0)` cache projection; `ConversationRequestController.load()` with one refresh per epoch and `ConversationLoadTrace` events.

- [ ] **Step 1: Add failing timing, cache, retry, and supersession tests**

```tsx
it("renders cached B immediately, settles by 10s, and ignores superseded A", async () => {
  const trace: string[] = [];
  const controller = makeController({ deadlineMs: 10_000, trace });
  controller.load(conversationA);
  await controller.load(conversationB);
  expect(trace).toContain("B:cache-rendered");
  vi.advanceTimersByTime(10_000);
  await flushPromises();
  expect(state.entries.B.loadPhase).toBe("error");
  expect(state.entries.B.freshness).toBe("stale");
  expect(state.entries.B.messages).toEqual(cachedB.messages);
  resolveA(liveA);
  expect(state.selectedKey).toBe("B");
  expect(state.entries.B.messages).toEqual(cachedB.messages);
});
```

```python
class SnapshotAcquisitionBudgetTest(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_transport_has_one_eight_second_acquisition_budget(self):
        with self.assertRaisesRegex(TransportError, "SNAPSHOT_ACQUISITION_TIMEOUT"):
            await self.transport.snapshot(deadline=self.fake_clock.monotonic() + 8.0)
        self.assertAlmostEqual(self.fake_clock.elapsed, 8.0, places=6)
        self.assertEqual(self.driver.calls.count("snapshot"), 1)
```

- [ ] **Step 2: Run tests to prove RED**

Run:
```bash
"$PYTHON" tests/test_transport_fixture.py
"$PYTHON" tests/test_transport_session_isolation.py
npm --prefix frontend run test:unit -- hooks/useConversationController.test.tsx
```
Expected: `FAIL`; the transport has no explicit snapshot budget/trace and failed refresh can combine stale cache with an ambiguous loading state.

- [ ] **Step 3: Implement one cache projection and one background refresh**

```ts
export interface ConversationLoadTrace {
  event: "selected" | "cache-rendered" | "refresh-started" | "deadline" | "settled-retry" | "superseded";
  identity: string;
  monotonic_ms: number;
}
```

On selection, dispatch `SELECT` so the reducer exposes the last verified snapshot synchronously, then start exactly one refresh for the new `(key, epoch)`. Pass the abort signal through both light and full requests. At 10 seconds, abort, clear loading, preserve cache, set one retryable error, and reject late completion. In Python, calculate one monotonic `deadline = monotonic() + 8.0` before selection/snapshot work and pass the remaining budget through every driver call; do not reset it on retry or content-script recovery.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the three commands from Step 2.
Expected: all selected tests `PASS`; each switch has one refresh, one terminal UI event, no stale+loading combination, and no superseded overwrite.

- [ ] **Step 5: Commit this isolated change**

```bash
git add transport/chatgpt_web/adapter.py console/chat.py frontend/hooks/useConversationController.ts frontend/lib/conversation-state.ts tests/test_transport_fixture.py tests/test_transport_session_isolation.py frontend/hooks/useConversationController.test.tsx
git commit -m "fix: bound cache-first conversation switching"
```

### Task 6: Add the isolated SnapshotFaultTransport and tagged browser trace

**Files:**
- Create: `transport/chatgpt_web/snapshot_fault.py`
- Modify: `console/chat.py:191-552`
- Modify: `frontend/e2e/fixtures/app.ts`
- Create: `frontend/e2e/runtime-browser-reliability.spec.ts`
- Test: `tests/test_transport_fixture.py`

**Interfaces:**
- Consumes: Task 5 `ConversationLoadTrace`; `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1`; required-storage state from `StorageContract(home).probe() -> StorageStatus` plus the verified marker location.
- Produces: `SnapshotFaultTransport(cached_snapshot: dict[str, object], *, fail_refreshes: int = 1, clock: Callable[[], float])`; it is constructible only when development fixtures are enabled and required storage is absent.

- [ ] **Step 1: Write failing fixture isolation tests**

```python
class SnapshotFaultTransportTest(unittest.IsolatedAsyncioTestCase):
    def test_snapshot_fault_transport_is_unreachable_in_product_runtime(self):
        with mock.patch.dict(os.environ, {"CORTEX_ALLOW_DEVELOPMENT_FIXTURES": "1"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "SNAPSHOT_FAULT_FIXTURE_FORBIDDEN"):
                make_snapshot_transport(storage=required_storage(), fault="timeout_once")

    async def test_snapshot_fault_returns_cache_then_times_out_exactly_one_refresh(self):
        transport = SnapshotFaultTransport(CACHED, fail_refreshes=1, clock=clock)
        self.assertEqual(await transport.cached_snapshot(), CACHED)
        with self.assertRaises(TimeoutError):
            await transport.refresh_snapshot(deadline=clock() + 8.0)
        self.assertEqual(await transport.refresh_snapshot(deadline=clock() + 8.0), LIVE)
```

- [ ] **Step 2: Run the fixture test to prove RED**

Run: `"$PYTHON" tests/test_transport_fixture.py`
Expected: `FAIL` because `snapshot_fault.py` and its construction gate do not exist.

- [ ] **Step 3: Implement the development-only fixture and Playwright trace**

```ts
test("@conversation-switch-fault cache survives one bounded refresh timeout", async ({ page }) => {
  await selectConversation(page, "Fault B");
  await expect(page.getByText("cached-B")).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toBeVisible({ timeout: 10_000 });
  const trace = await page.evaluate(() => window.__CORTEX_QA_TRACE__);
  expect(trace.map((row) => row.event)).toEqual([
    "selected", "cache-rendered", "refresh-started", "deadline", "settled-retry",
  ]);
});
```

Expose the trace only in the development fixture bundle. The test must also switch A→B before A resolves and assert `superseded` plus B content unchanged.

- [ ] **Step 4: Build fresh and run the tagged E2E**

Run:
```bash
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @conversation-switch-fault
```
Expected: fresh build succeeds; exactly the tagged test runs and `PASS`es with selected/cache/refresh/deadline/settled and supersession events.

- [ ] **Step 5: Commit this isolated change**

```bash
git add transport/chatgpt_web/snapshot_fault.py console/chat.py tests/test_transport_fixture.py frontend/e2e/fixtures/app.ts frontend/e2e/runtime-browser-reliability.spec.ts
git commit -m "test: cover bounded conversation refresh failure"
```

### Task 7: Track tab provenance and retire only a proven redundant Cortex reader

**Files:**
- Modify: `chrome-extension/service-worker-core.js:1-370,940-1664`
- Modify: `chrome-extension/service-worker.js:1-167`
- Modify: `console/chat.py:322-552`
- Test: `chrome-extension/tests/extension.test.mjs`
- Test: `tests/test_chrome_extension_bridge.py`
- Test: `tests/test_chrome_extension_driver.py`
- Test: `tests/test_chrome_extension_readiness_regression.py`

**Interfaces:**
- Consumes: current session IDs, canonical conversation identity, and transport delivery-uncertain classification.
- Produces: `TabProvenanceRecord { tab_id, generation, origin, role, session_id, conversation_identity, in_flight_commands }`; `recordTabCreated`, `beginTabCommand`, `finishTabCommand`, `canonicalizeWriter`, `forgetRemovedTab`, and `retireRedundantReader`.

- [ ] **Step 1: Add failing provenance regression tests**

```js
test("snapshot then send retires only the redundant Cortex reader", async () => {
  const context = contextWithProvenance();
  const reader = await allocateCortexReader(context, "conv-1");
  const writer = await allocateWriter(context, "conv-1");
  await canonicalizeWriter(context, writer.id, "conv-1");
  assert.deepEqual(context.chrome.tabs.removed, [reader.id]);
  assert.equal(await context.chrome.tabs.get(writer.id), writer);
});

test("restart, tab-id reuse, user origin, uncertainty, and active commands all fail closed", async () => {
  assert.equal((await retireAfterRestart()).removed.length, 0);
  assert.equal((await reuseRemovedId()).inheritedProvenance, false);
  assert.equal((await retireUserTab()).removed.length, 0);
  assert.equal((await retireUncertainWriter()).removed.length, 0);
  assert.equal((await retireBusyReader()).removed.length, 0);
});
```

- [ ] **Step 2: Run extension and backend tests to prove RED**

Run:
```bash
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_bridge.py
"$PYTHON" tests/test_chrome_extension_driver.py
"$PYTHON" tests/test_chrome_extension_readiness_regression.py
```
Expected: `FAIL`; the context has reusable/quarantined pools but no provenance generation or safe redundant-reader retirement.

- [ ] **Step 3: Implement fail-closed in-memory provenance**

```js
export function recordTabCreated(context, tab, { role, sessionId }) {
  const generation = (context.tabGenerations.get(tab.id) || 0) + 1;
  context.tabGenerations.set(tab.id, generation);
  context.tabProvenance.set(tab.id, {
    tab_id: tab.id, generation, origin: "cortex", role,
    session_id: sessionId, conversation_identity: null, in_flight_commands: 0,
  });
  return generation;
}

export async function retireRedundantReader(context, writer) {
  const candidate = [...context.tabProvenance.values()].find((row) =>
    row.origin === "cortex" && row.role === "read_only"
    && row.conversation_identity === writer.conversation_identity
    && row.in_flight_commands === 0 && row.tab_id !== writer.tab_id);
  if (candidate) await context.chrome.tabs.remove(candidate.tab_id);
}
```

Every existing tab discovered without a current record is `origin=user`. `tabs.onRemoved` receives the removed tab ID plus captured generation and removes only a matching current record. Service-worker startup does not reconstruct provenance from open tabs. Delivery-uncertain tabs remain quarantined and are neither reused nor retirement candidates. Two writers for distinct sessions remain open.

- [ ] **Step 4: Re-run tests to prove GREEN**

Run the four commands from Step 2.
Expected: all selected tests `PASS`; removal occurs once only for the proven redundant Cortex reader, never for user/unknown/busy/uncertain/reused tabs.

- [ ] **Step 5: Commit this isolated change**

```bash
git add chrome-extension/service-worker-core.js chrome-extension/service-worker.js console/chat.py chrome-extension/tests/extension.test.mjs tests/test_chrome_extension_bridge.py tests/test_chrome_extension_driver.py tests/test_chrome_extension_readiness_regression.py
git commit -m "fix: retire only proven redundant Cortex tabs"
```

### Task 8: Remove the unsupported archives control and preserve sidebar categories

**Files:**
- Modify: `frontend/components/ConversationSidebar.tsx:1-146`
- Test: `frontend/components/ConversationSidebar.test.tsx`

**Interfaces:**
- Consumes: `groupConversations()` categories `pinned`, `projects`, and `recent`.
- Produces: sidebar with `Nouvelle conversation`, search, pinned/project/recent groups, guide/history/settings; no archive affordance.

- [ ] **Step 1: Add the failing sidebar contract**

```tsx
it("keeps new, pinned, project and recent navigation without archives", async () => {
  renderSidebar(mixedConversations);
  expect(screen.getByRole("button", { name: /Nouvelle conversation/ })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Épinglées" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Projet Atlas" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Récentes" })).toBeVisible();
  expect(screen.queryByText("Conversations archivées")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the unit test to prove RED**

Run: `npm --prefix frontend run test:unit -- components/ConversationSidebar.test.tsx`
Expected: `FAIL` because the dead `Conversations archivées` button remains visible.

- [ ] **Step 3: Remove only the unsupported control**

Delete the `ArchiveIcon` import and `archived-button` element. Do not change `groupConversations`, search, collapsed navigation, project grouping, or `onNewConversation`.

- [ ] **Step 4: Re-run the unit test to prove GREEN**

Run: `npm --prefix frontend run test:unit -- components/ConversationSidebar.test.tsx`
Expected: all sidebar tests `PASS` and required category/new-chat controls remain usable.

- [ ] **Step 5: Commit this isolated change**

```bash
git add frontend/components/ConversationSidebar.tsx frontend/components/ConversationSidebar.test.tsx
git commit -m "fix: remove unsupported archives control"
```

### Task 9: Make diagnostic export observable and test its DOM lifecycle

**Files:**
- Modify: `frontend/components/SettingsPanel.tsx:69-190,306-324`
- Create: `frontend/components/SettingsPanel.diagnostic-export.test.tsx`
- Modify: `frontend/e2e/runtime-browser-reliability.spec.ts`

**Interfaces:**
- Consumes: existing `GET /api/diagnostics/export` payload.
- Produces: `requestDiagnosticDownload(fetcher, document, urlApi, defer) -> Promise<{ state: "requested"; filename: string } | { state: "failed"; message: string }>` and inline `DiagnosticDownloadState`.

- [ ] **Step 1: Write the failing DOM lifecycle tests**

```tsx
it("attaches and clicks one link, then removes and revokes it after dispatch", async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click");
  renderSettingsPanel();
  await user.click(screen.getByRole("button", { name: "Exporter le rapport" }));
  expect(click).toHaveBeenCalledTimes(1);
  expect(document.querySelector('a[download^="cortex-diagnostic-"]')).toBeNull();
  expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  await vi.runAllTimersAsync();
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status")).toHaveTextContent(/Téléchargement demandé.*\.json/);
});

it("shows an inline failure and never calls alert", async () => {
  server.use(failedDiagnosticExport());
  await user.click(screen.getByRole("button", { name: "Exporter le rapport" }));
  expect(window.alert).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("Impossible de préparer le téléchargement");
});
```

- [ ] **Step 2: Run the dedicated test to prove RED**

Run: `npm --prefix frontend run test:unit -- components/SettingsPanel.diagnostic-export.test.tsx`
Expected: `FAIL`; the current link is never attached, Blob URL is revoked synchronously, success is silent, and failure uses `window.alert`.

- [ ] **Step 3: Implement the observable download lifecycle**

```ts
export type DiagnosticDownloadState =
  | { state: "idle" }
  | { state: "requested"; filename: string }
  | { state: "failed"; message: string };
```

Append the anchor to `document.body`, click once, remove it in `finally`, and call `setTimeout(() => URL.revokeObjectURL(url), 0)`. Render `Téléchargement demandé : <filename>` with `role="status"`; render the bounded failure with `role="alert"`. Never claim that bytes were saved.

- [ ] **Step 4: Run unit and real-download E2E tests**

Run:
```bash
npm --prefix frontend run test:unit -- components/SettingsPanel.diagnostic-export.test.tsx
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @diagnostic-export
```
Expected: unit tests `PASS`; exactly one Playwright `download` event fires, the suggested filename equals the inline status, the file exists with non-zero JSON bytes, and the fixture privacy assertion passes.

- [ ] **Step 5: Commit this isolated change**

```bash
git add frontend/components/SettingsPanel.tsx frontend/components/SettingsPanel.diagnostic-export.test.tsx frontend/e2e/runtime-browser-reliability.spec.ts
git commit -m "fix: expose diagnostic download outcome"
```

### Task 10: Run the integrated runtime/UI/browser acceptance gates

**Files:**
- Modify: `scripts/test-all.sh`
- Create: `tests/test_ui_reliability_gate.py`
- Test: all files modified by Tasks 1-9

**Interfaces:**
- Consumes: every production and test interface from Tasks 1-9.
- Produces: one fresh static build and deterministic automated evidence that the repair domains compose without skipped suites.

- [ ] **Step 1: Write the failing aggregate-runner contract test**

```python
class UiReliabilityGateTest(unittest.TestCase):
    def test_aggregate_runner_contains_every_ui_reliability_gate(self):
        script = Path("scripts/test-all.sh").read_text(encoding="utf-8")
        for required in (
            "components/LocalAliasActionPanel.test.tsx",
            "@local-alias-ui", "@conversation-switch-fault", "@diagnostic-export",
            "tests/test_executor_runtime_truth.py", "tests/test_onboarding_runtime_truth.py",
            "tests/test_ui_reliability_gate.py",
            "tests/test_chrome_extension_readiness_regression.py",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() == 0:
        raise SystemExit("ZERO_TESTS_SELECTED")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
```

- [ ] **Step 2: Run the contract test to prove RED**

Run: `"$PYTHON" tests/test_ui_reliability_gate.py`
Expected: `FAIL` because the aggregate runner does not yet name every new focused/tagged gate; the runner prints `Ran 1 test` and `ZERO_TESTS_SELECTED` is impossible to report as success.

- [ ] **Step 3: Add required focused suites to the aggregate runner**

```bash
"$PYTHON" tests/test_onboarding_runtime_truth.py
"$PYTHON" tests/test_ui_reliability_gate.py
npm --prefix frontend run test:unit -- components/SettingsPanel.diagnostic-export.test.tsx
npm --prefix frontend run test:unit -- components/LocalAliasActionPanel.test.tsx components/ChatWorkspace.test.tsx
npm --prefix frontend run test:e2e -- --grep @local-alias-ui
npm --prefix frontend run test:e2e -- --grep @conversation-switch-fault
npm --prefix frontend run test:e2e -- --grep @diagnostic-export
```

Place these in `scripts/test-all.sh` after the fresh frontend build and normalization; propagate any non-zero status and reject zero selected tests.

- [ ] **Step 4: Run the complete focused, aggregate, and static GREEN gates**

Run:
```bash
"$PYTHON" tests/test_executor_runtime_truth.py
"$PYTHON" tests/test_onboarding_runtime_truth.py
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" tests/test_transport_fixture.py
"$PYTHON" tests/test_transport_session_isolation.py
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_bridge.py
"$PYTHON" tests/test_chrome_extension_driver.py
"$PYTHON" tests/test_chrome_extension_readiness_regression.py
npm --prefix frontend run test:unit -- components/CortexApp.integration.test.tsx components/OnboardingPanel.test.tsx components/SettingsPanel.regression-1.test.tsx components/ConversationSidebar.test.tsx components/SettingsPanel.diagnostic-export.test.tsx components/LocalAliasActionPanel.test.tsx components/ChatWorkspace.test.tsx hooks/useConversationController.test.tsx
npm --prefix frontend run test:runtime
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @local-alias-ui
npm --prefix frontend run test:e2e -- --grep @conversation-switch-fault
npm --prefix frontend run test:e2e -- --grep @diagnostic-export
"$PYTHON" tests/test_ui_reliability_gate.py
test -d frontend/node_modules
PYTHON="$PYTHON" scripts/test-all.sh
git diff --check
git status --short
```
Expected: every command exits zero; all three E2E selectors run at least one test; aggregate suite has no frontend skip; diff check is silent; status lists only reviewed implementation/test/doc files and no QA evidence.

- [ ] **Step 5: Commit the aggregate-runner wiring**

```bash
git add scripts/test-all.sh tests/test_ui_reliability_gate.py
git commit -m "test: gate runtime browser reliability repairs"
```

## Implementation Boundaries After Automated Tests

- Real-Chrome retests R1-R5 remain separate, action-time owner approvals. They are not performed by plan execution.
- R1 uses a disposable `CORTEX_HOME` for the missing-workspace case; R2 records monotonic real switches plus the isolated fault trace; R3 requires approval for neutral send and extension restart; R4 exercises new/pinned/project/recent; R5 proves a real download and scans its bytes.
- Screenshots must crop conversation content, personal sidebar data, raw URLs, and private paths. Missing real-browser evidence yields `UNCLEAR`, never an inferred `PASS`.
- No implementation task may modify the legacy sparsebundle, storage configuration, Chrome profile, running service, or current ChatGPT conversation.
