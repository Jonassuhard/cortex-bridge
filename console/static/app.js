/* Cortex Bridge Console — vanilla JS, no build step. */

const $ = (id) => document.getElementById(id);

const state = {
  tasks: [],
  currentId: null,
  eventSource: null,
  mode: "simulation",
  storageUnavailable: false,
};

/* ------------------------------------------------------------- helpers */

function relTime(iso) {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

function fmtTs(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour12: false });
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${opts?.method || "GET"} ${path} → ${res.status}`);
  return res.json();
}

/* ----------------------------------------------------------- status bar */

function setChip(el, text, cls) {
  el.textContent = text;
  el.className = "chip " + cls;
}

function renderRuntime(s) {
  $("rtEndpoint").textContent = s.endpoint || "—";
  $("rtStorage").textContent = s.storage_path || "—";
  $("rtPrimaryName").textContent = s.primary?.name || "—";
  $("rtFallbackName").textContent = s.fallback?.name || "—";

  for (const [id, m] of [["rtPrimaryState", s.primary], ["rtFallbackState", s.fallback]]) {
    const st = m?.state || "missing";
    setChip($(id), st, st === "loaded" ? "chip-state-loaded"
      : st === "installed" ? "chip-state" : "chip-state-missing");
  }

  setChip($("rtVolume"), s.volume_mounted ? "mounted" : "missing",
    s.volume_mounted ? "chip-ok" : "chip-bad");
  setChip($("rtOllama"), s.ollama_status || "unhealthy",
    s.ollama_status === "healthy" ? "chip-ok" : "chip-bad");

  state.storageUnavailable = s.storage_status === "LOCAL_MODEL_STORAGE_UNAVAILABLE";
  $("storageBanner").hidden = !state.storageUnavailable;
  $("runBtn").disabled = state.storageUnavailable;

  const bad = state.storageUnavailable || s.ollama_status !== "healthy";
  const chip = $("runtimeChip");
  chip.textContent = bad ? "degraded" : "OK";
  chip.classList.toggle("bad", bad);
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    state.mode = s.mode;
    $("ollamaDot").className = "dot " + (s.ollama_up ? "dot-up" : "dot-down");
    $("ollamaLabel").textContent = s.ollama_up ? "Ollama up" : "Ollama down";
    $("modelLabel").textContent = s.model;
    const chip = $("modeChip");
    chip.textContent = s.mode;
    chip.classList.toggle("live", s.mode === "live");
    $("simNote").hidden = s.mode !== "simulation";
    renderRuntime(s);
  } catch {
    $("ollamaDot").className = "dot dot-unknown";
    $("ollamaLabel").textContent = "Ollama ?";
  }
}

/* -------------------------------------------------------------- sidebar */

function renderTaskList() {
  const ul = $("taskList");
  ul.innerHTML = "";
  $("taskListEmpty").style.display = state.tasks.length ? "none" : "block";
  for (const t of state.tasks) {
    const li = document.createElement("li");
    li.className = "task-item" + (t.id === state.currentId ? " active" : "");
    const dot = document.createElement("span");
    dot.className = "dot dot-" + t.status;
    const body = document.createElement("div");
    body.className = "task-item-body";
    const goal = document.createElement("div");
    goal.className = "task-item-goal";
    goal.textContent = t.goal.length > 60 ? t.goal.slice(0, 60) + "…" : t.goal;
    const time = document.createElement("div");
    time.className = "task-item-time";
    time.textContent = relTime(t.started_at);
    body.append(goal, time);
    li.append(dot, body);
    li.addEventListener("click", () => selectTask(t.id));
    ul.appendChild(li);
  }
}

async function refreshTasks() {
  state.tasks = await api("/api/tasks");
  renderTaskList();
}

/* ------------------------------------------------------------- live log */

function appendLogLine(entry) {
  const view = $("logView");
  const line = document.createElement("div");
  line.className = "log-line kind-" + entry.kind;
  const ts = document.createElement("span");
  ts.className = "log-ts";
  ts.textContent = fmtTs(entry.ts);
  const text = document.createElement("span");
  text.textContent = entry.text;
  line.append(ts, text);
  view.appendChild(line);
  view.scrollTop = view.scrollHeight;
}

function attachStream(taskId) {
  if (state.eventSource) state.eventSource.close();
  $("logView").innerHTML = "";
  const es = new EventSource(`/api/tasks/${taskId}/stream`);
  state.eventSource = es;
  es.onmessage = (e) => appendLogLine(JSON.parse(e.data));
  es.addEventListener("done", async () => {
    es.close();
    state.eventSource = null;
    await refreshTasks();
    const task = await api(`/api/tasks/${taskId}`);
    renderReport(task);
  });
  es.onerror = () => { /* SSE auto-retries; ignore transient errors */ };
}

/* --------------------------------------------------------------- report */

function setPill(el, status, pop) {
  el.textContent = status.toUpperCase();
  el.className = "pill pill-" + status + (pop ? " pop" : "");
}

function fillList(el, items, emptyText) {
  el.innerHTML = "";
  if (!items || !items.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = emptyText;
    el.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  }
}

function renderReplies(task) {
  const section = $("repliesSection");
  const replies = task.orchestrator_replies || [];
  section.hidden = replies.length === 0;
  const ul = $("repliesList");
  ul.innerHTML = "";
  for (const r of replies) {
    const li = document.createElement("li");
    li.textContent = `[${fmtTs(r.ts)}] ${r.text}`;
    ul.appendChild(li);
  }
}

function renderReport(task) {
  const report = task.report;
  $("livePill").hidden = true;
  $("reportCard").hidden = false;
  setPill($("reportPill"), task.status, true);
  $("simBanner").hidden = !(report && report.mode === "simulation");
  $("reportGoal").textContent = task.goal;
  if (report) {
    $("reportSummary").textContent = report.summary || "—";
    fillList($("reportFiles"), report.files_changed, "No files changed");
    fillList($("reportBlockers"), report.blockers, "None");
    $("reportNext").textContent = report.suggested_next_step || "—";
  }
  renderReplies(task);
}

/* ----------------------------------------------------------- task flow */

async function selectTask(taskId) {
  state.currentId = taskId;
  renderTaskList();
  const task = await api(`/api/tasks/${taskId}`);
  $("liveCard").hidden = false;
  $("livePill").hidden = task.status !== "running";
  if (task.status === "running") {
    $("reportCard").hidden = true;
    attachStream(taskId);
  } else {
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    $("logView").innerHTML = "";
    for (const entry of task.logs || []) appendLogLine(entry);
    renderReport(task);
  }
}

async function runTask() {
  const goal = $("goalInput").value.trim();
  if (!goal) { $("goalInput").focus(); return; }
  if (state.storageUnavailable) return; // backend refuses with 409 anyway
  const constraints = $("constraintsInput").value
    .split(",").map((s) => s.trim()).filter(Boolean);
  const workspace = $("workspaceInput").value.trim() || "~/";
  $("runBtn").disabled = true;
  try {
    const created = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, constraints, workspace }),
    });
    await refreshTasks();
    await selectTask(created.id);
  } finally {
    $("runBtn").disabled = state.storageUnavailable;
  }
}

/* --------------------------------------------------- orchestrator reply */

async function copyReport() {
  const task = await api(`/api/tasks/${state.currentId}`);
  const payload = JSON.stringify({
    task_id: task.id,
    goal: task.goal,
    report: task.report,
  }, null, 2);
  try {
    await navigator.clipboard.writeText(payload);
    $("copiedHint").hidden = false;
    setTimeout(() => { $("copiedHint").hidden = true; }, 2000);
  } catch {
    window.prompt("Copy the report manually:", payload);
  }
}

async function submitReply() {
  const text = $("replyInput").value.trim();
  if (!text) return;
  await api(`/api/tasks/${state.currentId}/orchestrator-reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  $("replyInput").value = "";
  $("replyForm").hidden = true;
  const task = await api(`/api/tasks/${state.currentId}`);
  renderReplies(task);
}

/* ----------------------------------------------------------------- init */

$("runBtn").addEventListener("click", runTask);
$("copyBtn").addEventListener("click", copyReport);
$("pasteBtn").addEventListener("click", () => { $("replyForm").hidden = false; $("replyInput").focus(); });
$("replyCancel").addEventListener("click", () => { $("replyForm").hidden = true; });
$("replySubmit").addEventListener("click", submitReply);
$("newTaskBtn").addEventListener("click", () => {
  state.currentId = null;
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
  renderTaskList();
  $("liveCard").hidden = true;
  $("reportCard").hidden = true;
  $("goalInput").focus();
});

refreshStatus();
refreshTasks();
setInterval(refreshStatus, 10000);
