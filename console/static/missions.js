/* Cortex Bridge — autonomous mission UI (Phase 6) */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const TERMINAL = new Set(["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]);
  const STATE_COLORS = {
    COMPLETED: "#16a34a", FAILED: "#dc2626", CANCELLED: "#64748b",
    BLOCKED: "#d97706", PAUSED: "#d97706", PAUSED_RECOVERY_REQUIRED: "#d97706",
    WAITING_FOR_APPROVAL: "#2563eb", WAITING_FOR_CHATGPT: "#8b5cf6",
  };

  let selectedMission = null;
  let pollTimer = null;

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(body.detail || res.statusText), { status: res.status, body });
    return body;
  }

  function toast(msg) {
    const el = $("conversationHint");
    if (el) { el.textContent = msg; setTimeout(() => { if (el.textContent === msg) el.textContent = ""; }, 8000); }
  }

  // ---------------------------------------------------------- transport §6

  async function refreshTransportStatus() {
    try {
      const s = await api("/api/transport/status");
      const chip = $("transportChip");
      chip.textContent = s.opt_in_accepted ? "enabled" : "disabled";
      chip.style.background = s.opt_in_accepted ? "#dcfce7" : "#fee2e2";
      chip.style.color = s.opt_in_accepted ? "#166534" : "#991b1b";
      $("transportWarning").hidden = s.opt_in_accepted;
      $("transportWarningText").textContent = s.experimental_warning;
      $("optinCheckbox").checked = s.opt_in_accepted;
      $("globalStopBanner").hidden = !s.global_stop;
      $("runMissionBtn").disabled = !s.opt_in_accepted || s.global_stop;
      $("missionOptinNote").hidden = s.opt_in_accepted && !s.global_stop;
      if (!s.opt_in_accepted) $("missionOptinNote").textContent = "Enable the experimental transport above first.";
      else if (s.global_stop) $("missionOptinNote").textContent = "STOP EVERYTHING is active.";
      $("stopEverythingBtn").classList.toggle("armed-off", s.global_stop);
    } catch (e) { /* console offline */ }
  }

  $("optinCheckbox").addEventListener("change", async (ev) => {
    await api("/api/transport/opt-in", { method: "POST", body: JSON.stringify({ accepted: ev.target.checked }) });
    refreshTransportStatus();
  });

  $("stopEverythingBtn").addEventListener("click", async () => {
    if (!confirm("STOP EVERYTHING?\n\nNo more browser messages, no more local actions. Evidence is preserved.")) return;
    await api("/api/transport/stop-everything", { method: "POST" });
    refreshTransportStatus();
    if (selectedMission) loadMissionDetail(selectedMission);
  });

  $("stopResetBtn").addEventListener("click", async () => {
    await api("/api/transport/stop-reset", { method: "POST" });
    refreshTransportStatus();
  });

  // ------------------------------------------------------------- composer

  $("refreshConversationsBtn").addEventListener("click", loadConversations);

  async function loadConversations() {
    const sel = $("conversationSelect");
    sel.innerHTML = "";
    const hint = $("conversationHint");
    hint.textContent = "Reading Chrome via WebBridge…";
    try {
      const convs = await api("/api/conversations");
      const fresh = document.createElement("option");
      fresh.value = "https://chatgpt.com/";
      fresh.dataset.fresh = "1";
      fresh.textContent = "＋ New conversation (fresh chat, created on first send)";
      sel.appendChild(fresh);
      for (const c of convs) {
        const o = document.createElement("option");
        o.value = c.url;
        o.textContent = `${c.title || "(untitled)"} — ${c.url}`;
        sel.appendChild(o);
      }
      hint.textContent = convs.length ? `${convs.length} conversation(s) found.` : "No chatgpt.com tab found — open one in Chrome, or pick “New conversation”.";
    } catch (e) {
      hint.textContent = `Cannot list conversations: ${e.message}. Open chatgpt.com in Chrome with WebBridge connected.`;
      const fresh = document.createElement("option");
      fresh.value = "https://chatgpt.com/";
      fresh.dataset.fresh = "1";
      fresh.textContent = "＋ New conversation (fresh chat)";
      sel.appendChild(fresh);
    }
  }

  $("runMissionBtn").addEventListener("click", async () => {
    const sel = $("conversationSelect");
    const payload = {
      objective: $("missionInput").value,
      workspace: $("missionWorkspace").value,
      constraints: $("missionConstraints").value.split(",").map((s) => s.trim()).filter(Boolean),
      conversation_url: sel.value,
      new_conversation: !!sel.selectedOptions[0]?.dataset.fresh,
      max_iterations: parseInt($("maxIterationsInput").value, 10) || 25,
      max_duration_minutes: parseInt($("maxDurationInput").value, 10) || 60,
      approval_policy: $("approvalPolicySelect").value,
    };
    if (!payload.objective.trim()) { toast("Mission objective is empty."); return; }
    if (!payload.conversation_url) { toast("Select a conversation first (Refresh)."); return; }
    $("runMissionBtn").disabled = true;
    try {
      const r = await api("/api/missions", { method: "POST", body: JSON.stringify(payload) });
      await loadMissions();
      selectMission(r.id);
    } catch (e) {
      toast(`Cannot start mission: ${e.message}`);
    } finally {
      $("runMissionBtn").disabled = false;
    }
  });

  // --------------------------------------------------------- missions list

  $("refreshMissionsBtn").addEventListener("click", loadMissions);

  async function loadMissions() {
    const list = $("missionList");
    const missions = await api("/api/missions");
    list.innerHTML = "";
    $("missionListEmpty").hidden = missions.length > 0;
    for (const m of missions) {
      const li = document.createElement("li");
      if (m.id === selectedMission) li.classList.add("selected");
      const obj = document.createElement("span");
      obj.className = "m-obj";
      obj.textContent = m.objective;
      const right = document.createElement("span");
      right.innerHTML = `<span class="m-id">${m.id.slice(0, 8)}</span> `;
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = m.state;
      pill.style.background = (STATE_COLORS[m.state] || "#334155") + "22";
      pill.style.color = STATE_COLORS[m.state] || "#334155";
      right.appendChild(pill);
      li.appendChild(obj);
      li.appendChild(right);
      li.addEventListener("click", () => selectMission(m.id));
      list.appendChild(li);
    }
  }

  // ------------------------------------------------------ mission detail

  function selectMission(id) {
    selectedMission = id;
    $("missionDetailCard").hidden = false;
    loadMissions();
    if (pollTimer) clearInterval(pollTimer);
    loadMissionDetail(id);
    pollTimer = setInterval(() => loadMissionDetail(id), 1500);
  }

  function ts(row) {
    for (const k of ["created_at", "started_at", "selected_at", "updated_at", "finished_at"]) {
      if (typeof row[k] === "number") return row[k];
    }
    return 0;
  }

  function fmtTs(t) {
    return t ? new Date(t * 1000).toLocaleTimeString() : "";
  }

  function tlEvent(kind, cls, headline, row) {
    const div = document.createElement("div");
    div.className = `tl-event ${cls}`;
    const head = document.createElement("div");
    head.className = "tl-head";
    head.innerHTML = `<span class="tl-kind">${kind}</span><span class="tl-ts">${fmtTs(ts(row))}</span>`;
    div.appendChild(head);
    const body = document.createElement("div");
    body.className = "tl-body";
    body.textContent = headline;
    div.appendChild(body);
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = "raw evidence";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(row, null, 2);
    det.appendChild(sum); det.appendChild(pre);
    div.appendChild(det);
    div._ts = ts(row);
    return div;
  }

  function renderTimeline(t) {
    const tl = $("missionTimeline");
    tl.innerHTML = "";
    const events = [];
    for (const b of t.conversation_bindings || [])
      events.push(tlEvent("conversation", "tl-transport", `Locked: ${b.conversation_title || b.conversation_url}`, b));
    for (const d of t.orchestrator_decisions || []) {
      let parsed = {};
      try { parsed = JSON.parse(d.decision_json || d.raw_json || "{}"); } catch (_) {}
      const label = parsed.state
        ? `${parsed.state}${parsed.action?.tool ? " → " + parsed.action.tool : ""} — ${parsed.summary || ""}`
        : (d.valid ? "decision" : "invalid decision");
      events.push(tlEvent("ChatGPT decision", "tl-decision", label, d));
    }
    for (const p of t.policy_decisions || [])
      events.push(tlEvent("policy", "tl-policy",
        `${p.tool}: ${p.allowed ? "allowed" : "DENIED"}${p.requires_approval ? " (approval required)" : ""} — ${p.reason || ""}`, p));
    for (const a of t.approvals || [])
      events.push(tlEvent("approval", "tl-approval", `${a.tool}: ${a.granted ? "granted (" + a.scope + ")" : "rejected"}`, a));
    for (const x of t.tool_executions || [])
      events.push(tlEvent("tool", "tl-tool", `${x.tool} ${x.arguments_json || ""} → exit ${x.exit_code}`, x));
    for (const v of t.validation_results || [])
      events.push(tlEvent("validation", v.passed ? "tl-validation-ok" : "tl-validation-ko",
        v.passed ? "passed" : "FAILED", v));
    for (const e of t.transport_events || [])
      events.push(tlEvent("transport", "tl-transport", e.event_type, e));
    events.sort((a, b) => a._ts - b._ts);
    for (const ev of events) tl.appendChild(ev);
  }

  async function loadMissionDetail(id) {
    let d;
    try { d = await api(`/api/missions/${id}`); } catch (e) { return; }
    const m = d.mission;
    $("missionDetailId").textContent = id.slice(0, 8);
    $("missionObjective").textContent = m.objective;
    const pill = $("missionStatePill");
    pill.textContent = m.state + (m.pause_reason ? ` — ${m.pause_reason}` : "");
    pill.style.background = (STATE_COLORS[m.state] || "#334155") + "22";
    pill.style.color = STATE_COLORS[m.state] || "#334155";
    $("resumeMissionBtn").hidden = !(m.state === "PAUSED" || m.state === "PAUSED_RECOVERY_REQUIRED");
    $("pauseMissionBtn").hidden = TERMINAL.has(m.state) || m.state === "PAUSED" || m.state === "PAUSED_RECOVERY_REQUIRED";
    $("cancelMissionBtn").hidden = TERMINAL.has(m.state);

    const panel = $("approvalPanel");
    if (d.awaiting_approval) {
      panel.hidden = false;
      const last = (d.timeline.policy_decisions || []).slice(-1)[0] || {};
      $("approvalDetail").textContent = `Tool "${last.tool || "?"}" requires approval — ${last.reason || ""}`;
    } else panel.hidden = true;

    renderTimeline(d.timeline);
    if (TERMINAL.has(m.state) && pollTimer) { clearInterval(pollTimer); pollTimer = null; loadMissions(); }
  }

  $("pauseMissionBtn").addEventListener("click", () =>
    api(`/api/missions/${selectedMission}/pause`, { method: "POST" }).then(() => loadMissionDetail(selectedMission)).catch((e) => toast(e.message)));
  $("resumeMissionBtn").addEventListener("click", () =>
    api(`/api/missions/${selectedMission}/resume`, { method: "POST" }).then(() => loadMissionDetail(selectedMission)).catch((e) => toast(e.message)));
  $("cancelMissionBtn").addEventListener("click", () =>
    api(`/api/missions/${selectedMission}/cancel`, { method: "POST" }).then(() => loadMissionDetail(selectedMission)).catch((e) => toast(e.message)));

  document.querySelectorAll("#approvalPanel [data-scope]").forEach((btn) =>
    btn.addEventListener("click", () =>
      api(`/api/missions/${selectedMission}/approve`, { method: "POST", body: JSON.stringify({ scope: btn.dataset.scope, approve: true }) })
        .then(() => loadMissionDetail(selectedMission)).catch((e) => toast(e.message))));
  $("rejectApprovalBtn").addEventListener("click", () =>
    api(`/api/missions/${selectedMission}/approve`, { method: "POST", body: JSON.stringify({ scope: "once", approve: false }) })
      .then(() => loadMissionDetail(selectedMission)).catch((e) => toast(e.message)));

  $("downloadReportBtn").addEventListener("click", async () => {
    const d = await api(`/api/missions/${selectedMission}/report`);
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `cortex-mission-${selectedMission.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  $("fallbackPayloadBtn").addEventListener("click", async () => {
    const d = await api(`/api/missions/${selectedMission}/fallback-payload`);
    await navigator.clipboard.writeText(d.payload);
    toast("Manual fallback payload copied — paste it in ChatGPT if the transport is down.");
  });

  // ------------------------------------------------------------------ init

  refreshTransportStatus();
  loadMissions();
  setInterval(refreshTransportStatus, 5000);
})();
