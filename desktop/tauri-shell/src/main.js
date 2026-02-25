import { invoke } from "@tauri-apps/api/core";

const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_REFRESH_INTERVAL_MS = 5000;
const hasTauri = typeof window !== "undefined" && !!window.__TAURI_INTERNALS__;

const baseUrlInput = document.querySelector("#baseUrl");
const tokenInput = document.querySelector("#token");
const autoRefreshInput = document.querySelector("#autoRefresh");
const refreshBtn = document.querySelector("#refreshBtn");
const objectiveInput = document.querySelector("#objectiveInput");
const strategySelect = document.querySelector("#strategySelect");
const candidatesInput = document.querySelector("#candidatesInput");
const executeToggle = document.querySelector("#executeToggle");
const runAsyncBtn = document.querySelector("#runAsyncBtn");
const createPlanBtn = document.querySelector("#createPlanBtn");
const plansEl = document.querySelector("#plans");
const jobsEl = document.querySelector("#jobs");
const eventsEl = document.querySelector("#events");
const summaryEl = document.querySelector("#summary");
const actionStatusEl = document.querySelector("#actionStatus");
const planCountEl = document.querySelector("#planCount");
const jobCountEl = document.querySelector("#jobCount");
const eventCountEl = document.querySelector("#eventCount");

let refreshTimer = null;

function currentConfig() {
  return {
    baseUrl: (baseUrlInput?.value || DEFAULT_BASE_URL).trim(),
    token: (tokenInput?.value || "").trim(),
  };
}

function saveConfig() {
  const { baseUrl, token } = currentConfig();
  localStorage.setItem("novaadapt.desktop.baseUrl", baseUrl);
  localStorage.setItem("novaadapt.desktop.token", token);
  localStorage.setItem("novaadapt.desktop.objective", (objectiveInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.strategy", strategySelect?.value || "single");
  localStorage.setItem("novaadapt.desktop.candidates", (candidatesInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.execute", executeToggle?.checked ? "1" : "0");
  localStorage.setItem("novaadapt.desktop.autoRefresh", autoRefreshInput?.checked ? "1" : "0");
}

function loadConfig() {
  baseUrlInput.value = localStorage.getItem("novaadapt.desktop.baseUrl") || DEFAULT_BASE_URL;
  tokenInput.value = localStorage.getItem("novaadapt.desktop.token") || "";
  objectiveInput.value = localStorage.getItem("novaadapt.desktop.objective") || "";
  strategySelect.value = localStorage.getItem("novaadapt.desktop.strategy") || "single";
  candidatesInput.value = localStorage.getItem("novaadapt.desktop.candidates") || "";
  executeToggle.checked = (localStorage.getItem("novaadapt.desktop.execute") || "0") === "1";
  autoRefreshInput.checked = (localStorage.getItem("novaadapt.desktop.autoRefresh") || "1") !== "0";
}

async function coreRequest(method, path, payload = null) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const { baseUrl, token } = currentConfig();
  if (hasTauri) {
    return invoke("core_request", {
      method: String(method || "GET"),
      baseUrl,
      token: token || null,
      path: normalizedPath,
      payload,
    });
  }

  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (payload !== null) headers["Content-Type"] = "application/json";

  const response = await fetch(`${baseUrl.replace(/\/$/, "")}${normalizedPath}`, {
    method: String(method || "GET").toUpperCase(),
    headers,
    body: payload === null ? undefined : JSON.stringify(payload),
  });

  const raw = await response.text();
  let parsed;
  try {
    parsed = raw ? JSON.parse(raw) : {};
  } catch {
    parsed = { raw };
  }
  if (!response.ok) {
    throw new Error(`Core API ${response.status}: ${typeof parsed === "object" ? JSON.stringify(parsed) : String(parsed)}`);
  }
  return parsed;
}

async function dashboardData() {
  return coreRequest("GET", "/dashboard/data?plans_limit=100&jobs_limit=100&events_limit=50");
}

function parseCandidates(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildObjectivePayload() {
  const objective = (objectiveInput?.value || "").trim();
  if (!objective) throw new Error("Objective is required");

  const strategy = String(strategySelect?.value || "single").trim() || "single";
  const payload = {
    objective,
    strategy,
    execute: Boolean(executeToggle?.checked),
    metadata: {
      source: "desktop-tauri",
      created_at: new Date().toISOString(),
    },
  };

  const candidates = parseCandidates(candidatesInput?.value || "");
  if (strategy === "vote" && candidates.length > 0) {
    payload.candidates = candidates;
  }
  return payload;
}

async function queueRun() {
  return coreRequest("POST", "/run_async", buildObjectivePayload());
}

async function createPlan() {
  return coreRequest("POST", "/plans", buildObjectivePayload());
}

async function approvePlan(planId, execute = true) {
  return coreRequest("POST", `/plans/${encodeURIComponent(planId)}/approve`, { execute });
}

async function rejectPlan(planId, reason) {
  return coreRequest("POST", `/plans/${encodeURIComponent(planId)}/reject`, {
    reason: reason || "Operator rejected",
  });
}

async function undoPlan(planId, execute = false, markOnly = true) {
  return coreRequest("POST", `/plans/${encodeURIComponent(planId)}/undo`, {
    execute,
    mark_only: markOnly,
  });
}

async function cancelJob(jobId) {
  return coreRequest("POST", `/jobs/${encodeURIComponent(jobId)}/cancel`, {});
}

function setActionStatus(message, kind = "neutral") {
  const text = String(message || "").trim() || "Idle";
  actionStatusEl.textContent = text;
  actionStatusEl.className = `badge ${kind}`;
}

function setBusy(value) {
  const busy = Boolean(value);
  refreshBtn.disabled = busy;
  runAsyncBtn.disabled = busy;
  createPlanBtn.disabled = busy;
  for (const btn of document.querySelectorAll("[data-mutate='1']")) {
    btn.disabled = busy;
  }
}

async function runAction(label, fn, refreshAfter = true) {
  setBusy(true);
  saveConfig();
  setActionStatus(label, "neutral");
  try {
    const out = await fn();
    setActionStatus(`${label} OK`, "ok");
    if (refreshAfter) {
      await refresh();
    }
    return out;
  } catch (err) {
    setActionStatus(`${label} failed`, "error");
    summaryEl.textContent = String(err?.message || err);
    throw err;
  } finally {
    setBusy(false);
  }
}

function sortPlans(plans) {
  const order = {
    pending: 0,
    executing: 1,
    approved: 2,
    failed: 3,
    executed: 4,
    rejected: 5,
  };
  return [...plans].sort((a, b) => {
    const left = order[String(a?.status || "").toLowerCase()] ?? 99;
    const right = order[String(b?.status || "").toLowerCase()] ?? 99;
    if (left !== right) return left - right;
    return String(b?.id || "").localeCompare(String(a?.id || ""));
  });
}

function renderPlans(plans) {
  const items = sortPlans(Array.isArray(plans) ? plans : []);
  const pending = items.filter((item) => String(item.status || "").toLowerCase() === "pending");
  planCountEl.textContent = String(pending.length);

  if (!items.length) {
    plansEl.innerHTML = "<p>No plans available.</p>";
    return;
  }

  plansEl.innerHTML = "";
  for (const plan of items.slice(0, 20)) {
    const status = String(plan.status || "").toLowerCase();
    const actionLogCount = Array.isArray(plan.action_log_ids) ? plan.action_log_ids.length : 0;
    const card = document.createElement("article");
    card.className = "plan";
    card.innerHTML = `
      <div class="plan-head">
        <strong>${escapeHTML(plan.objective || "(no objective)")}</strong>
        <span class="plan-id">${escapeHTML(plan.id || "")}</span>
      </div>
      <p class="plan-meta">
        <span class="status">${escapeHTML(status || "unknown")}</span>
        • Strategy: ${escapeHTML(plan.strategy || "single")}
        • Actions: ${(plan.actions || []).length}
        • Progress: ${Number(plan.progress_completed || 0)}/${Number(plan.progress_total || 0)}
      </p>
      ${plan.execution_error ? `<p class="plan-meta">Error: ${escapeHTML(plan.execution_error)}</p>` : ""}
      <div class="row"></div>
    `;

    const actionRow = card.querySelector(".row");
    if (status === "pending") {
      actionRow.appendChild(
        actionButton("Approve + Execute", "secondary", async () => {
          await runAction("Approving plan", () => approvePlan(plan.id, true));
        }),
      );
      actionRow.appendChild(
        actionButton("Reject", "danger", async () => {
          const reason = window.prompt("Reject reason", "Operator rejected");
          if (!reason) return;
          await runAction("Rejecting plan", () => rejectPlan(plan.id, reason));
        }),
      );
    }

    if (actionLogCount > 0) {
      actionRow.appendChild(
        actionButton("Undo (Mark Only)", "secondary", async () => {
          await runAction("Marking plan undone", () => undoPlan(plan.id, false, true));
        }),
      );
      actionRow.appendChild(
        actionButton("Undo + Execute", "danger", async () => {
          const confirmText = window.confirm("Execute all undo actions for this plan?");
          if (!confirmText) return;
          await runAction("Executing plan undo", () => undoPlan(plan.id, true, false));
        }),
      );
    }

    plansEl.appendChild(card);
  }
}

function renderJobs(jobs) {
  const items = Array.isArray(jobs) ? jobs : [];
  const active = items.filter((item) => {
    const status = String(item.status || "").toLowerCase();
    return status === "queued" || status === "running";
  });
  jobCountEl.textContent = String(active.length);

  if (!items.length) {
    jobsEl.innerHTML = "<p>No jobs available.</p>";
    return;
  }

  jobsEl.innerHTML = "";
  const order = { running: 0, queued: 1, failed: 2, succeeded: 3, canceled: 4 };
  const sorted = [...items].sort((a, b) => {
    const left = order[String(a.status || "").toLowerCase()] ?? 99;
    const right = order[String(b.status || "").toLowerCase()] ?? 99;
    if (left !== right) return left - right;
    return String(b.id || "").localeCompare(String(a.id || ""));
  });

  for (const job of sorted.slice(0, 20)) {
    const status = String(job.status || "unknown").toLowerCase();
    const card = document.createElement("article");
    card.className = "plan";
    card.innerHTML = `
      <div class="plan-head">
        <strong>${escapeHTML(job.kind || "run")}</strong>
        <span class="plan-id">${escapeHTML(job.id || "")}</span>
      </div>
      <p class="plan-meta"><span class="status">${escapeHTML(status)}</span></p>
      <div class="row"></div>
    `;
    const row = card.querySelector(".row");
    if (status === "queued" || status === "running") {
      row.appendChild(
        actionButton("Cancel", "danger", async () => {
          await runAction("Canceling job", () => cancelJob(job.id));
        }),
      );
    }
    jobsEl.appendChild(card);
  }
}

function renderEvents(events) {
  const items = Array.isArray(events) ? events : [];
  eventCountEl.textContent = String(items.length);
  if (!items.length) {
    eventsEl.innerHTML = "<p>No events recorded.</p>";
    return;
  }
  eventsEl.innerHTML = "";
  for (const event of items.slice(0, 25)) {
    const card = document.createElement("article");
    card.className = "event";
    card.innerHTML = `
      <div class="event-head">
        <strong>${escapeHTML(event.category || "event")} / ${escapeHTML(event.action || "")}</strong>
        <span>${escapeHTML(formatTimestamp(event.created_at))}</span>
      </div>
      <p class="event-meta">Status: ${escapeHTML(event.status || "unknown")} • ID: ${escapeHTML(event.id || "")}</p>
    `;
    eventsEl.appendChild(card);
  }
}

function renderSummary(data) {
  const plans = Array.isArray(data?.plans) ? data.plans : [];
  const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
  const events = Array.isArray(data?.events) ? data.events : [];

  const out = {
    health: data?.health,
    models_count: data?.models_count,
    pending_plans: plans.filter((item) => String(item.status || "").toLowerCase() === "pending").length,
    active_jobs: jobs.filter((item) => ["queued", "running"].includes(String(item.status || "").toLowerCase()))
      .length,
    events_loaded: events.length,
    metrics: data?.metrics || {},
  };
  summaryEl.textContent = JSON.stringify(out, null, 2);
}

function render(data) {
  renderPlans(data?.plans || []);
  renderJobs(data?.jobs || []);
  renderEvents(data?.events || []);
  renderSummary(data || {});
}

async function refresh() {
  saveConfig();
  const data = await dashboardData();
  render(data);
}

function startAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (!autoRefreshInput.checked) return;
  refreshTimer = window.setInterval(() => {
    refresh().catch((err) => {
      setActionStatus("Auto refresh failed", "error");
      summaryEl.textContent = String(err?.message || err);
    });
  }, DEFAULT_REFRESH_INTERVAL_MS);
}

function actionButton(label, kind, onClick) {
  const btn = document.createElement("button");
  btn.className = kind;
  btn.textContent = label;
  btn.dataset.mutate = "1";
  btn.addEventListener("click", onClick);
  return btn;
}

function formatTimestamp(value) {
  if (!value) return "-";
  const dt = new Date(String(value));
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

refreshBtn.addEventListener("click", () => {
  runAction("Refreshing", () => refresh(), false).catch(() => {});
});
runAsyncBtn.addEventListener("click", () => {
  runAction("Queueing objective", () => queueRun(), true).catch(() => {});
});
createPlanBtn.addEventListener("click", () => {
  runAction("Creating plan", () => createPlan(), true).catch(() => {});
});
baseUrlInput.addEventListener("change", saveConfig);
tokenInput.addEventListener("change", saveConfig);
objectiveInput.addEventListener("change", saveConfig);
strategySelect.addEventListener("change", saveConfig);
candidatesInput.addEventListener("change", saveConfig);
executeToggle.addEventListener("change", saveConfig);
autoRefreshInput.addEventListener("change", () => {
  saveConfig();
  startAutoRefresh();
});

loadConfig();
setActionStatus("Idle", "neutral");
refresh()
  .catch((err) => {
    setActionStatus("Initial refresh failed", "error");
    summaryEl.textContent = String(err?.message || err);
  })
  .finally(() => startAutoRefresh());

window.addEventListener("beforeunload", () => {
  if (refreshTimer) window.clearInterval(refreshTimer);
});
