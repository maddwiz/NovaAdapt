import { invoke } from "@tauri-apps/api/core";

const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_REFRESH_INTERVAL_MS = 5000;
const DEFAULT_REQUEST_TIMEOUT_MS = 20000;
const hasTauri = typeof window !== "undefined" && !!window.__TAURI_INTERNALS__;

const baseUrlInput = document.querySelector("#baseUrl");
const tokenInput = document.querySelector("#token");
const rememberTokenInput = document.querySelector("#rememberToken");
const autoRefreshInput = document.querySelector("#autoRefresh");
const testConnectionBtn = document.querySelector("#testConnectionBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const liveStreamBtn = document.querySelector("#liveStreamBtn");
const objectiveInput = document.querySelector("#objectiveInput");
const strategySelect = document.querySelector("#strategySelect");
const candidatesInput = document.querySelector("#candidatesInput");
const executeToggle = document.querySelector("#executeToggle");
const autoRepairAttemptsInput = document.querySelector("#autoRepairAttemptsInput");
const repairStrategySelect = document.querySelector("#repairStrategySelect");
const repairModelInput = document.querySelector("#repairModelInput");
const repairCandidatesInput = document.querySelector("#repairCandidatesInput");
const repairFallbacksInput = document.querySelector("#repairFallbacksInput");
const runAsyncBtn = document.querySelector("#runAsyncBtn");
const createPlanBtn = document.querySelector("#createPlanBtn");
const plansEl = document.querySelector("#plans");
const jobsEl = document.querySelector("#jobs");
const eventsEl = document.querySelector("#events");
const controlArtifactsEl = document.querySelector("#controlArtifacts");
const summaryEl = document.querySelector("#summary");
const actionStatusEl = document.querySelector("#actionStatus");
const planCountEl = document.querySelector("#planCount");
const jobCountEl = document.querySelector("#jobCount");
const eventCountEl = document.querySelector("#eventCount");
const artifactCountEl = document.querySelector("#artifactCount");
const connectionStatusEl = document.querySelector("#connectionStatus");
const liveStreamStatusEl = document.querySelector("#liveStreamStatus");
const governanceStatusEl = document.querySelector("#governanceStatus");
const budgetLimitInput = document.querySelector("#budgetLimitInput");
const maxActiveRunsInput = document.querySelector("#maxActiveRunsInput");
const refreshGovernanceBtn = document.querySelector("#refreshGovernanceBtn");
const applyGovernanceBtn = document.querySelector("#applyGovernanceBtn");
const pauseRuntimeBtn = document.querySelector("#pauseRuntimeBtn");
const resumeRuntimeBtn = document.querySelector("#resumeRuntimeBtn");
const resetUsageBtn = document.querySelector("#resetUsageBtn");
const cancelAllJobsBtn = document.querySelector("#cancelAllJobsBtn");
const governanceOutputEl = document.querySelector("#governanceOutput");
const iotStatusEl = document.querySelector("#iotStatus");
const entityDomainInput = document.querySelector("#entityDomainInput");
const entityPrefixInput = document.querySelector("#entityPrefixInput");
const refreshEntitiesBtn = document.querySelector("#refreshEntitiesBtn");
const refreshMqttStatusBtn = document.querySelector("#refreshMqttStatusBtn");
const iotEntitiesEl = document.querySelector("#iotEntities");
const mqttTopicInput = document.querySelector("#mqttTopicInput");
const mqttPayloadInput = document.querySelector("#mqttPayloadInput");
const mqttRetainInput = document.querySelector("#mqttRetainInput");
const mqttPublishBtn = document.querySelector("#mqttPublishBtn");
const mqttSubscribeBtn = document.querySelector("#mqttSubscribeBtn");
const mqttOutputEl = document.querySelector("#mqttOutput");
const templateStatusEl = document.querySelector("#templateStatus");
const templateTagInput = document.querySelector("#templateTagInput");
const templateManifestInput = document.querySelector("#templateManifestInput");
const refreshTemplatesBtn = document.querySelector("#refreshTemplatesBtn");
const exportTemplateBtn = document.querySelector("#exportTemplateBtn");
const importTemplateBtn = document.querySelector("#importTemplateBtn");
const templateLibraryEl = document.querySelector("#templateLibrary");
const templateGalleryEl = document.querySelector("#templateGallery");
const templateOutputEl = document.querySelector("#templateOutput");

let refreshTimer = null;
let liveRefreshTimer = null;
let refreshInFlight = false;
let queuedRefresh = false;
let scheduledRefreshTimer = null;
const liveState = {
  enabled: false,
  connected: false,
  lastAuditId: 0,
  consecutiveErrors: 0,
};

function normalizeBaseUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) throw new Error("Base URL is required");
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("Base URL must be a valid http(s) URL");
  }
  const scheme = parsed.protocol.toLowerCase();
  if (scheme !== "http:" && scheme !== "https:") {
    throw new Error("Base URL scheme must be http or https");
  }
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function currentConfig() {
  return {
    baseUrl: normalizeBaseUrl(baseUrlInput?.value || DEFAULT_BASE_URL),
    token: (tokenInput?.value || "").trim(),
  };
}

function saveConfig() {
  let baseUrl = DEFAULT_BASE_URL;
  try {
    baseUrl = normalizeBaseUrl(baseUrlInput?.value || DEFAULT_BASE_URL);
  } catch {
    baseUrl = DEFAULT_BASE_URL;
  }
  const token = (tokenInput?.value || "").trim();
  localStorage.setItem("novaadapt.desktop.baseUrl", baseUrl);
  localStorage.setItem("novaadapt.desktop.rememberToken", rememberTokenInput?.checked ? "1" : "0");
  if (rememberTokenInput?.checked) {
    localStorage.setItem("novaadapt.desktop.token", token);
  } else {
    localStorage.removeItem("novaadapt.desktop.token");
  }
  localStorage.setItem("novaadapt.desktop.objective", (objectiveInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.strategy", strategySelect?.value || "single");
  localStorage.setItem("novaadapt.desktop.candidates", (candidatesInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.execute", executeToggle?.checked ? "1" : "0");
  localStorage.setItem("novaadapt.desktop.autoRepairAttempts", (autoRepairAttemptsInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.repairStrategy", repairStrategySelect?.value || "decompose");
  localStorage.setItem("novaadapt.desktop.repairModel", (repairModelInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.repairCandidates", (repairCandidatesInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.repairFallbacks", (repairFallbacksInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.autoRefresh", autoRefreshInput?.checked ? "1" : "0");
  localStorage.setItem("novaadapt.desktop.liveStream", liveState.enabled ? "1" : "0");
  localStorage.setItem("novaadapt.desktop.budgetLimit", (budgetLimitInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.maxActiveRuns", (maxActiveRunsInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.iotDomain", (entityDomainInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.iotPrefix", (entityPrefixInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.mqttTopic", (mqttTopicInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.mqttPayload", mqttPayloadInput?.value || "");
  localStorage.setItem("novaadapt.desktop.mqttRetain", mqttRetainInput?.checked ? "1" : "0");
  localStorage.setItem("novaadapt.desktop.templateTag", (templateTagInput?.value || "").trim());
  localStorage.setItem("novaadapt.desktop.templateManifest", templateManifestInput?.value || "");
}

function loadConfig() {
  const rememberedBase = localStorage.getItem("novaadapt.desktop.baseUrl") || DEFAULT_BASE_URL;
  try {
    baseUrlInput.value = normalizeBaseUrl(rememberedBase);
  } catch {
    baseUrlInput.value = DEFAULT_BASE_URL;
  }
  const rememberToken = (localStorage.getItem("novaadapt.desktop.rememberToken") || "0") === "1";
  rememberTokenInput.checked = rememberToken;
  tokenInput.value = rememberToken ? (localStorage.getItem("novaadapt.desktop.token") || "") : "";
  objectiveInput.value = localStorage.getItem("novaadapt.desktop.objective") || "";
  strategySelect.value = localStorage.getItem("novaadapt.desktop.strategy") || "single";
  candidatesInput.value = localStorage.getItem("novaadapt.desktop.candidates") || "";
  executeToggle.checked = (localStorage.getItem("novaadapt.desktop.execute") || "0") === "1";
  autoRepairAttemptsInput.value = localStorage.getItem("novaadapt.desktop.autoRepairAttempts") || "0";
  repairStrategySelect.value = localStorage.getItem("novaadapt.desktop.repairStrategy") || "decompose";
  repairModelInput.value = localStorage.getItem("novaadapt.desktop.repairModel") || "";
  repairCandidatesInput.value = localStorage.getItem("novaadapt.desktop.repairCandidates") || "";
  repairFallbacksInput.value = localStorage.getItem("novaadapt.desktop.repairFallbacks") || "";
  autoRefreshInput.checked = (localStorage.getItem("novaadapt.desktop.autoRefresh") || "1") !== "0";
  liveState.enabled = (localStorage.getItem("novaadapt.desktop.liveStream") || "0") === "1";
  budgetLimitInput.value = localStorage.getItem("novaadapt.desktop.budgetLimit") || "";
  maxActiveRunsInput.value = localStorage.getItem("novaadapt.desktop.maxActiveRuns") || "";
  entityDomainInput.value = localStorage.getItem("novaadapt.desktop.iotDomain") || "";
  entityPrefixInput.value = localStorage.getItem("novaadapt.desktop.iotPrefix") || "";
  mqttTopicInput.value = localStorage.getItem("novaadapt.desktop.mqttTopic") || "";
  mqttPayloadInput.value = localStorage.getItem("novaadapt.desktop.mqttPayload") || "";
  mqttRetainInput.checked = (localStorage.getItem("novaadapt.desktop.mqttRetain") || "0") === "1";
  templateTagInput.value = localStorage.getItem("novaadapt.desktop.templateTag") || "";
  templateManifestInput.value = localStorage.getItem("novaadapt.desktop.templateManifest") || "";
}

async function coreRequest(method, path, payload = null) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const { baseUrl, token } = currentConfig();
  if (hasTauri) {
    return requestWithRetries(async () =>
      invoke("core_request", {
        method: String(method || "GET"),
        baseUrl,
        token: token || null,
        path: normalizedPath,
        payload,
      }),
    );
  }

  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (payload !== null) headers["Content-Type"] = "application/json";

  const response = await requestWithRetries(() =>
    fetchWithTimeout(`${baseUrl.replace(/\/$/, "")}${normalizedPath}`, {
      method: String(method || "GET").toUpperCase(),
      headers,
      body: payload === null ? undefined : JSON.stringify(payload),
    }),
  );

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

async function fetchWithTimeout(url, options) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

async function requestWithRetries(fn, maxAttempts = 3) {
  let lastError = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const out = await fn();
      if (!out || typeof out.status !== "number") {
        return out;
      }
      if ([429, 502, 503, 504].includes(out.status) && attempt < maxAttempts) {
        await sleep(150 * attempt);
        continue;
      }
      return out;
    } catch (error) {
      lastError = error;
      if (attempt >= maxAttempts) break;
      await sleep(150 * attempt);
    }
  }
  throw lastError || new Error("request failed");
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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

function buildRepairOptions() {
  const payload = {};
  const attempts = Number.parseInt(String(autoRepairAttemptsInput?.value || "0").trim() || "0", 10);
  if (Number.isFinite(attempts) && attempts > 0) {
    payload.auto_repair_attempts = attempts;
  }
  const repairStrategy = String(repairStrategySelect?.value || "decompose").trim();
  if (repairStrategy) {
    payload.repair_strategy = repairStrategy;
  }
  const repairModel = String(repairModelInput?.value || "").trim();
  if (repairModel) {
    payload.repair_model = repairModel;
  }
  const repairCandidates = parseCandidates(repairCandidatesInput?.value || "");
  if (repairCandidates.length > 0) {
    payload.repair_candidates = repairCandidates;
  }
  const repairFallbacks = parseCandidates(repairFallbacksInput?.value || "");
  if (repairFallbacks.length > 0) {
    payload.repair_fallbacks = repairFallbacks;
  }
  return payload;
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
    ...buildRepairOptions(),
  };

  const candidates = parseCandidates(candidatesInput?.value || "");
  if (candidates.length > 0) {
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

async function approvePlan(planId, payload = { execute: true }) {
  return coreRequest("POST", `/plans/${encodeURIComponent(planId)}/approve`, payload);
}

async function retryFailedPlan(planId, payload) {
  return coreRequest("POST", `/plans/${encodeURIComponent(planId)}/retry_failed_async`, payload);
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

function setConnectionStatus(message, kind = "neutral") {
  const text = String(message || "").trim() || "Not connected";
  connectionStatusEl.textContent = text;
  connectionStatusEl.className = `badge ${kind}`;
}

function setGovernanceStatus(message, kind = "neutral") {
  if (!governanceStatusEl) return;
  const text = String(message || "").trim() || "Unknown";
  governanceStatusEl.textContent = text;
  governanceStatusEl.className = `badge ${kind}`;
}

function setLiveStatus(message, kind = "neutral") {
  if (!liveStreamStatusEl) return;
  const text = String(message || "").trim() || "Live idle";
  liveStreamStatusEl.textContent = text;
  liveStreamStatusEl.className = `badge ${kind}`;
}

function setIoTStatus(message, kind = "neutral") {
  if (!iotStatusEl) return;
  const text = String(message || "").trim() || "Idle";
  iotStatusEl.textContent = text;
  iotStatusEl.className = `badge ${kind}`;
}

function setTemplateStatus(message, kind = "neutral") {
  if (!templateStatusEl) return;
  const text = String(message || "").trim() || "Idle";
  templateStatusEl.textContent = text;
  templateStatusEl.className = `badge ${kind}`;
}

function updateLiveButton() {
  if (!liveStreamBtn) return;
  liveStreamBtn.textContent = liveState.enabled ? "Live On" : "Live Off";
  liveStreamBtn.className = liveState.enabled ? "primary" : "secondary";
}

function setBusy(value) {
  const busy = Boolean(value);
  refreshBtn.disabled = busy;
  testConnectionBtn.disabled = busy;
  runAsyncBtn.disabled = busy;
  createPlanBtn.disabled = busy;
  if (refreshGovernanceBtn) refreshGovernanceBtn.disabled = busy;
  if (applyGovernanceBtn) applyGovernanceBtn.disabled = busy;
  if (pauseRuntimeBtn) pauseRuntimeBtn.disabled = busy;
  if (resumeRuntimeBtn) resumeRuntimeBtn.disabled = busy;
  if (resetUsageBtn) resetUsageBtn.disabled = busy;
  if (cancelAllJobsBtn) cancelAllJobsBtn.disabled = busy;
  if (refreshEntitiesBtn) refreshEntitiesBtn.disabled = busy;
  if (refreshMqttStatusBtn) refreshMqttStatusBtn.disabled = busy;
  if (mqttPublishBtn) mqttPublishBtn.disabled = busy;
  if (mqttSubscribeBtn) mqttSubscribeBtn.disabled = busy;
  for (const btn of document.querySelectorAll("[data-mutate='1']")) {
    btn.disabled = busy;
  }
}

function extractMaxAuditId(items) {
  let maxId = liveState.lastAuditId;
  for (const item of Array.isArray(items) ? items : []) {
    const value = Number.parseInt(String(item?.id ?? "").trim(), 10);
    if (Number.isFinite(value)) {
      maxId = Math.max(maxId, value);
    }
  }
  return maxId;
}

function scheduleRefresh(delayMs = 150) {
  if (scheduledRefreshTimer) window.clearTimeout(scheduledRefreshTimer);
  scheduledRefreshTimer = window.setTimeout(() => {
    scheduledRefreshTimer = null;
    refresh().catch((err) => {
      setActionStatus("Live refresh failed", "error");
      summaryEl.textContent = String(err?.message || err);
    });
  }, Math.max(0, Number(delayMs || 0)));
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

function countResultsByStatus(results) {
  const counts = {};
  for (const item of Array.isArray(results) ? results : []) {
    const status = String(item?.status || "unknown").toLowerCase();
    counts[status] = (counts[status] || 0) + 1;
  }
  return counts;
}

function summarizeRepair(repair, results) {
  const counts = countResultsByStatus(results);
  const repairedCount = Number(counts.repaired || 0);
  if (!repair || typeof repair !== "object") {
    return repairedCount > 0 ? `${repairedCount} repaired action${repairedCount === 1 ? "" : "s"}` : "";
  }
  const attempts = Number(repair.attempts || 0);
  const unresolved = Array.isArray(repair.failed_indexes) ? repair.failed_indexes.length : 0;
  const healed = Boolean(repair.healed);
  const parts = [];
  if (healed) {
    parts.push("auto-repair healed");
  } else if (attempts > 0) {
    parts.push("auto-repair attempted");
  }
  if (repairedCount > 0) parts.push(`${repairedCount} repaired`);
  if (attempts > 0) parts.push(`${attempts} attempt${attempts === 1 ? "" : "s"}`);
  if (unresolved > 0 && !healed) parts.push(`${unresolved} unresolved`);
  if (repair.last_error && !healed) parts.push(String(repair.last_error));
  return parts.join(" • ");
}

function summarizeCollaboration(voteSummary, collaboration, fallbackStrategy) {
  const vote = voteSummary && typeof voteSummary === "object" ? voteSummary : {};
  const collab = collaboration && typeof collaboration === "object" ? collaboration : {};
  const mode = String(collab.mode || fallbackStrategy || "").toLowerCase();
  if (vote.subtasks_total !== undefined || mode === "decompose") {
    const total = Number(vote.subtasks_total || 0);
    const succeeded = Number(vote.subtasks_succeeded || 0);
    const reviewed = Number(vote.reviewed_subtasks || 0);
    const batches = Number(vote.parallel_batches || 0);
    const parts = ["decompose"];
    if (total > 0) parts.push(`${succeeded}/${total} subtasks`);
    if (reviewed > 0) parts.push(`${reviewed} reviewed`);
    if (batches > 0) parts.push(`${batches} batches`);
    if (vote.reason) parts.push(String(vote.reason).replaceAll("_", " "));
    return parts.join(" • ");
  }
  if (vote.winner_votes !== undefined || mode === "vote") {
    const winnerVotes = Number(vote.winner_votes || 0);
    const totalVotes = Number(vote.total_votes || 0);
    const parts = ["vote"];
    if (totalVotes > 0) parts.push(`${winnerVotes}/${totalVotes} votes`);
    if (vote.quorum_met) parts.push("quorum");
    return parts.join(" • ");
  }
  return "";
}

function transcriptPreviewLines(collaboration, limit = 3) {
  const collab = collaboration && typeof collaboration === "object" ? collaboration : {};
  const transcript = Array.isArray(collab.transcript) ? collab.transcript : [];
  return transcript
    .map((item) => {
      const type = String(item?.type || "").toLowerCase();
      if (type === "subtask_started") {
        const subtaskId = String(item?.subtask_id || "subtask");
        const model = String(item?.model || "");
        return `started ${subtaskId}${model ? ` with ${model}` : ""}`;
      }
      if (type === "subtask_output") {
        const subtaskId = String(item?.subtask_id || "subtask");
        const model = String(item?.model || "model");
        const attempt = Number(item?.attempt || 1);
        return `output ${subtaskId} • ${model} • attempt ${attempt}`;
      }
      if (type === "subtask_review") {
        const reviewer = String(item?.reviewer_model || "reviewer");
        const subtaskId = String(item?.subtask_id || "subtask");
        return `${reviewer} ${item?.approved ? "approved" : "rejected"} ${subtaskId}`;
      }
      if (type === "subtask_failed") {
        const subtaskId = String(item?.subtask_id || "subtask");
        const error = String(item?.error || "failed");
        return `${subtaskId} failed • ${error}`;
      }
      if (type === "synthesis") {
        return `synthesis by ${String(item?.model || "model")}`;
      }
      return "";
    })
    .filter(Boolean)
    .slice(0, limit);
}

function summarizeJobResult(result, fallbackKind = "run") {
  const payload = result && typeof result === "object" ? result : null;
  if (!payload) return "";
  const counts = countResultsByStatus(payload.results);
  const parts = [];
  const strategy = String(payload.strategy || "");
  const model = String(payload.model || "");
  if (strategy) parts.push(strategy);
  if (model) parts.push(model);
  const total = Array.isArray(payload.results) ? payload.results.length : 0;
  if (total > 0) {
    parts.push(`${total} actions`);
    if (counts.ok) parts.push(`${counts.ok} ok`);
    if (counts.preview) parts.push(`${counts.preview} preview`);
    if (counts.repaired) parts.push(`${counts.repaired} repaired`);
    const failed = Number(counts.failed || 0) + Number(counts.blocked || 0);
    if (failed > 0) parts.push(`${failed} failed`);
  } else if (fallbackKind) {
    parts.push(String(fallbackKind));
  }
  return parts.join(" • ");
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
    const repairSummary = summarizeRepair(plan.repair, plan.execution_results);
    const collaborationSummary = summarizeCollaboration(plan.vote_summary, plan.collaboration, plan.strategy);
    const transcriptLines = transcriptPreviewLines(plan.collaboration);
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
      ${repairSummary ? `<p class="plan-meta">Repair: ${escapeHTML(repairSummary)}</p>` : ""}
      ${collaborationSummary ? `<p class="plan-meta">Collab: ${escapeHTML(collaborationSummary)}</p>` : ""}
      ${transcriptLines.length ? `<div class="plan-meta">${transcriptLines.map((line) => `• ${escapeHTML(line)}`).join("<br />")}</div>` : ""}
      <div class="row"></div>
    `;

    const actionRow = card.querySelector(".row");
    if (status === "pending") {
      actionRow.appendChild(
        actionButton("Approve + Execute", "secondary", async () => {
          await runAction("Approving plan", () => approvePlan(plan.id, { execute: true, ...buildRepairOptions() }));
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

    if (status === "failed") {
      actionRow.appendChild(
        actionButton("Retry Failed Steps", "secondary", async () => {
          const confirmed = window.confirm(
            "Retry only failed/blocked actions for this plan with dangerous actions enabled?",
          );
          if (!confirmed) return;
          await runAction("Queueing failed-step retry", () =>
            retryFailedPlan(plan.id, {
              allow_dangerous: true,
              action_retry_attempts: 2,
              action_retry_backoff_seconds: 0.2,
              ...buildRepairOptions(),
            }),
          );
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
    const metadata = job.metadata && typeof job.metadata === "object" ? job.metadata : {};
    const kind = String(job.kind || metadata.kind || "run");
    const objective = String(job.objective || metadata.objective || "");
    const result = job.result && typeof job.result === "object" ? job.result : null;
    const resultSummary = summarizeJobResult(result, kind);
    const repairSummary = summarizeRepair(result?.repair, result?.results);
    const collaborationSummary = summarizeCollaboration(result?.vote_summary, result?.collaboration, result?.strategy || kind);
    const transcriptLines = transcriptPreviewLines(result?.collaboration);
    const card = document.createElement("article");
    card.className = "plan";
    card.innerHTML = `
      <div class="plan-head">
        <strong>${escapeHTML(kind)}</strong>
        <span class="plan-id">${escapeHTML(job.id || "")}</span>
      </div>
      <p class="plan-meta"><span class="status">${escapeHTML(status)}</span></p>
      ${objective ? `<p class="plan-meta">${escapeHTML(objective)}</p>` : ""}
      ${resultSummary ? `<p class="plan-meta">${escapeHTML(resultSummary)}</p>` : ""}
      ${job.error ? `<p class="plan-meta">Error: ${escapeHTML(job.error)}</p>` : ""}
      ${repairSummary ? `<p class="plan-meta">Repair: ${escapeHTML(repairSummary)}</p>` : ""}
      ${collaborationSummary ? `<p class="plan-meta">Collab: ${escapeHTML(collaborationSummary)}</p>` : ""}
      ${transcriptLines.length ? `<div class="plan-meta">${transcriptLines.map((line) => `• ${escapeHTML(line)}`).join("<br />")}</div>` : ""}
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

function artifactPreviewUrl(path) {
  if (!path) return "";
  const { baseUrl, token } = currentConfig();
  const normalizedPath = String(path).startsWith("/") ? String(path) : `/${String(path)}`;
  const prefix = baseUrl.replace(/\/$/, "");
  if (!token) return `${prefix}${normalizedPath}`;
  const sep = normalizedPath.includes("?") ? "&" : "?";
  return `${prefix}${normalizedPath}${sep}token=${encodeURIComponent(token)}`;
}

function renderControlArtifacts(items) {
  const artifacts = Array.isArray(items) ? items : [];
  artifactCountEl.textContent = String(artifacts.length);
  if (!artifacts.length) {
    controlArtifactsEl.innerHTML = "<p>No control artifacts available.</p>";
    return;
  }
  controlArtifactsEl.innerHTML = "";
  for (const artifact of artifacts.slice(0, 8)) {
    const card = document.createElement("article");
    card.className = "event";
    const preview = artifact.preview_available && artifact.preview_path
      ? `<img class="artifact-preview" src="${escapeHTML(artifactPreviewUrl(artifact.preview_path))}" alt="artifact preview" loading="lazy" />`
      : "";
    card.innerHTML = `
      ${preview}
      <div class="event-head">
        <strong>${escapeHTML([artifact.control_type || "control", artifact.platform || artifact.transport || artifact.action_type || "preview"].filter(Boolean).join(" / "))}</strong>
        <span>${escapeHTML(formatTimestamp(artifact.created_at))}</span>
      </div>
      <p class="event-meta">Status: ${escapeHTML(artifact.status || "unknown")} • Goal: ${escapeHTML(artifact.goal || artifact.output_preview || "(no goal)")}</p>
      <p class="event-meta">Action: ${escapeHTML(artifact.action_type || "unknown")}${artifact.target ? ` • ${escapeHTML(artifact.target)}` : ""}</p>
      <p class="event-meta">Model: ${escapeHTML(artifact.model || "n/a")}${artifact.dangerous ? " • dangerous" : ""}</p>
    `;
    controlArtifactsEl.appendChild(card);
  }
}

function renderGovernance(governance) {
  const data = governance && typeof governance === "object" ? governance : {};
  const paused = Boolean(data.paused);
  setGovernanceStatus(paused ? "Paused" : "Active", paused ? "error" : "ok");
  if (budgetLimitInput && !document.activeElement?.isSameNode(budgetLimitInput)) {
    const budget = data.budget_limit_usd;
    budgetLimitInput.value = budget === null || budget === undefined ? "" : String(budget);
  }
  if (maxActiveRunsInput && !document.activeElement?.isSameNode(maxActiveRunsInput)) {
    const maxActiveRuns = data.max_active_runs;
    maxActiveRunsInput.value = maxActiveRuns === null || maxActiveRuns === undefined ? "" : String(maxActiveRuns);
  }
  if (!governanceOutputEl) return;
  governanceOutputEl.textContent = JSON.stringify(
    {
      paused,
      pause_reason: data.pause_reason || "",
      active_runs: data.active_runs || 0,
      jobs: data.jobs || {},
      llm_calls_total: data.llm_calls_total || 0,
      runs_total: data.runs_total || 0,
      spend_estimate_usd: data.spend_estimate_usd || 0,
      budget_limit_usd: data.budget_limit_usd,
      max_active_runs: data.max_active_runs,
      per_model: data.per_model || {},
      last_strategy: data.last_strategy || "",
      last_objective_preview: data.last_objective_preview || "",
      last_run_at: data.last_run_at || "",
      updated_at: data.updated_at || "",
    },
    null,
    2,
  );
}

async function refreshGovernance() {
  saveConfig();
  const result = await coreRequest("GET", "/runtime/governance");
  renderGovernance(result);
  return result;
}

async function applyGovernanceLimits() {
  saveConfig();
  const payload = {};
  const budgetRaw = String(budgetLimitInput?.value || "").trim();
  const maxRaw = String(maxActiveRunsInput?.value || "").trim();
  payload.budget_limit_usd = budgetRaw ? Number(budgetRaw) : null;
  payload.max_active_runs = maxRaw ? Number(maxRaw) : null;
  const result = await coreRequest("POST", "/runtime/governance", payload);
  renderGovernance(result);
  return result;
}

async function pauseRuntime() {
  const reason = window.prompt("Pause reason", "Operator pause") || "Operator pause";
  const result = await coreRequest("POST", "/runtime/governance", {
    paused: true,
    pause_reason: reason,
  });
  renderGovernance(result);
  return result;
}

async function resumeRuntime() {
  const result = await coreRequest("POST", "/runtime/governance", {
    paused: false,
    pause_reason: "",
  });
  renderGovernance(result);
  return result;
}

async function resetGovernanceUsage() {
  const result = await coreRequest("POST", "/runtime/governance", { reset_usage: true });
  renderGovernance(result);
  return result;
}

async function cancelAllJobs() {
  const confirmed = window.confirm("Cancel all queued/running jobs and pause the runtime first?");
  if (!confirmed) return null;
  const result = await coreRequest("POST", "/runtime/jobs/cancel_all", {
    pause: true,
    pause_reason: "Operator cancel all",
  });
  if (result?.governance) {
    renderGovernance(result.governance);
  }
  return result;
}

function quickActionsForEntity(entity) {
  const entityId = String(entity?.entity_id || "");
  const domain = entityId.split(".", 1)[0] || "";
  const state = String(entity?.state || "").toLowerCase();
  if (domain === "light" || domain === "switch" || domain === "input_boolean") {
    return [
      { label: "Turn On", service: "turn_on" },
      { label: state === "on" ? "Turn Off" : "Turn Off", service: "turn_off" },
      { label: "Toggle", service: "toggle" },
    ];
  }
  if (domain === "cover") {
    return [
      { label: "Open", service: "open_cover" },
      { label: "Close", service: "close_cover" },
      { label: "Stop", service: "stop_cover" },
    ];
  }
  if (domain === "vacuum") {
    return [
      { label: "Start", service: "start" },
      { label: "Pause", service: "pause" },
      { label: "Dock", service: "return_to_base" },
    ];
  }
  if (domain === "script" || domain === "scene") {
    return [{ label: "Run", service: "turn_on" }];
  }
  return [{ label: "Execute", service: "turn_on" }];
}

function renderMQTTOutput(payload, fallback = "No MQTT activity yet.") {
  if (!mqttOutputEl) return;
  if (payload === null || payload === undefined || payload === "") {
    mqttOutputEl.textContent = fallback;
    return;
  }
  if (typeof payload === "string") {
    mqttOutputEl.textContent = payload;
    return;
  }
  mqttOutputEl.textContent = JSON.stringify(payload, null, 2);
}

function renderTemplateOutput(payload, fallback = "No template activity yet.") {
  if (!templateOutputEl) return;
  if (payload === null || payload === undefined || payload === "") {
    templateOutputEl.textContent = fallback;
    return;
  }
  if (typeof payload === "string") {
    templateOutputEl.textContent = payload;
    return;
  }
  templateOutputEl.textContent = JSON.stringify(payload, null, 2);
}

function renderIoTEntities(result) {
  const entities = Array.isArray(result?.entities) ? result.entities : [];
  if (!iotEntitiesEl) return;
  if (!entities.length) {
    iotEntitiesEl.innerHTML = "<p>No entities matched the current filters.</p>";
    return;
  }
  iotEntitiesEl.innerHTML = "";
  for (const entity of entities.slice(0, 18)) {
    const entityId = String(entity?.entity_id || "");
    const domain = entityId.split(".", 1)[0] || "";
    const attrs = entity?.attributes && typeof entity.attributes === "object" ? entity.attributes : {};
    const friendlyName = String(attrs.friendly_name || entityId || "Entity");
    const card = document.createElement("article");
    card.className = "iot-entity";
    card.innerHTML = `
      <div class="event-head">
        <strong>${escapeHTML(friendlyName)}</strong>
        <span>${escapeHTML(String(entity?.state ?? "unknown"))}</span>
      </div>
      <p class="event-meta">${escapeHTML(entityId)}</p>
      <p class="event-meta">${escapeHTML(summarizeEntityAttributes(attrs))}</p>
      <div class="row"></div>
    `;
    const row = card.querySelector(".row");
    for (const action of quickActionsForEntity(entity)) {
      row.appendChild(
        actionButton(action.label, "secondary", async () => {
          const confirmed = window.confirm(`Execute ${domain}.${action.service} for ${entityId}?`);
          if (!confirmed) return;
          await runAction(`Executing ${domain}.${action.service}`, async () => {
            const response = await coreRequest("POST", "/iot/homeassistant/action", {
              action: {
                type: "ha_service",
                domain,
                service: action.service,
                entity_id: entityId,
              },
              execute: true,
            });
            renderMQTTOutput(response, "Service executed.");
            await refreshIoTEntities();
          }, false);
        }),
      );
    }
    iotEntitiesEl.appendChild(card);
  }
}

function summarizeEntityAttributes(attributes) {
  const entries = [];
  const friendly = String(attributes?.friendly_name || "").trim();
  if (friendly) entries.push(`Name: ${friendly}`);
  for (const key of ["device_class", "unit_of_measurement", "brightness", "temperature", "current_position"]) {
    const value = attributes?.[key];
    if (value !== undefined && value !== null && `${value}`.trim() !== "") {
      entries.push(`${key}: ${value}`);
    }
    if (entries.length >= 4) break;
  }
  return entries.length ? entries.join(" • ") : "No additional attributes";
}

async function refreshIoTEntities() {
  saveConfig();
  const domain = encodeURIComponent((entityDomainInput?.value || "").trim());
  const prefix = encodeURIComponent((entityPrefixInput?.value || "").trim());
  const query = [`limit=24`];
  if (domain) query.push(`domain=${domain}`);
  if (prefix) query.push(`entity_id_prefix=${prefix}`);
  const result = await coreRequest("GET", `/iot/homeassistant/entities?${query.join("&")}`);
  renderIoTEntities(result);
  setIoTStatus(`Loaded ${Number(result?.count || 0)} entities`, "ok");
  return result;
}

async function refreshMQTTStatus() {
  saveConfig();
  const result = await coreRequest("GET", "/iot/mqtt/status");
  const host = String(result?.host || result?.broker || "broker");
  const kind = result?.ok ? "ok" : "error";
  setIoTStatus(result?.ok ? `MQTT ${host}` : "MQTT unavailable", kind);
  renderMQTTOutput(result, "MQTT status unavailable.");
  return result;
}

async function publishMQTT() {
  const topic = String(mqttTopicInput?.value || "").trim();
  if (!topic) throw new Error("MQTT topic is required");
  saveConfig();
  const confirmed = window.confirm(`Publish to MQTT topic ${topic}?`);
  if (!confirmed) return null;
  const result = await coreRequest("POST", "/iot/mqtt/publish", {
    topic,
    payload: mqttPayloadInput?.value || "",
    retain: Boolean(mqttRetainInput?.checked),
    execute: true,
  });
  renderMQTTOutput(result, "MQTT publish complete.");
  setIoTStatus(`Published ${topic}`, "ok");
  return result;
}

async function subscribeMQTTSnapshot() {
  const topic = String(mqttTopicInput?.value || "").trim();
  if (!topic) throw new Error("MQTT topic is required");
  saveConfig();
  const result = await coreRequest("POST", "/iot/mqtt/subscribe", {
    topic,
    timeout_seconds: 1.5,
    max_messages: 6,
    qos: 0,
  });
  renderMQTTOutput(result, "No MQTT messages received.");
  setIoTStatus(`Subscribed ${topic}`, "ok");
  return result;
}

function templateTagQuery() {
  const tag = String(templateTagInput?.value || "").trim();
  return tag ? `?tag=${encodeURIComponent(tag)}` : "";
}

function summarizeTemplate(template) {
  const tags = Array.isArray(template?.tags) ? template.tags.filter(Boolean).join(", ") : "";
  const strategy = String(template?.strategy || "single");
  const source = String(template?.source || "local");
  const memory = Array.isArray(template?.memory_snapshot) ? template.memory_snapshot.length : 0;
  const parts = [`strategy ${strategy}`, `source ${source}`];
  if (tags) parts.push(`tags ${tags}`);
  if (memory > 0) parts.push(`memory ${memory}`);
  return parts.join(" • ");
}

function renderTemplateCards(container, templates, actionsFactory, emptyMessage) {
  if (!container) return;
  const items = Array.isArray(templates) ? templates : [];
  if (!items.length) {
    container.innerHTML = `<p>${escapeHTML(emptyMessage)}</p>`;
    return;
  }
  container.innerHTML = "";
  for (const template of items) {
    const templateId = String(template?.template_id || template?.id || "");
    const card = document.createElement("article");
    card.className = "plan";
    card.innerHTML = `
      <div class="plan-head">
        <strong>${escapeHTML(String(template?.name || templateId || "Template"))}</strong>
        <span>${escapeHTML(String(template?.updated_at || template?.created_at || templateId || ""))}</span>
      </div>
      <p class="plan-meta">${escapeHTML(String(template?.description || template?.objective || "(no description)"))}</p>
      <p class="plan-meta">${escapeHTML(summarizeTemplate(template))}</p>
      <p class="plan-meta">${escapeHTML(String(template?.objective || "(no objective)"))}</p>
      <div class="row"></div>
    `;
    const actionRow = card.querySelector(".row");
    for (const action of actionsFactory(template)) {
      actionRow.appendChild(
        actionButton(action.label, action.kind || "secondary", async () => {
          await action.onClick(template);
        }),
      );
    }
    container.appendChild(card);
  }
}

function renderTemplateLibrary(payload) {
  renderTemplateCards(
    templateLibraryEl,
    payload?.templates || [],
    (template) => [
      {
        label: "Plan",
        kind: "secondary",
        onClick: async () => {
          await runAction(`Launching template ${template.name} as plan`, async () => {
            const result = await coreRequest("POST", `/agents/templates/${encodeURIComponent(template.template_id)}/launch`, {
              mode: "plan",
              execute: false,
              context: "desktop-tauri",
            });
            renderTemplateOutput(result, "Template plan launch complete.");
            await refresh();
          }, true);
        },
      },
      {
        label: "Run",
        kind: "primary",
        onClick: async () => {
          const confirmed = window.confirm(`Launch ${template.name} as an immediate run?`);
          if (!confirmed) return;
          await runAction(`Launching template ${template.name} as run`, async () => {
            const result = await coreRequest("POST", `/agents/templates/${encodeURIComponent(template.template_id)}/launch`, {
              mode: "run",
              execute: true,
              context: "desktop-tauri",
            });
            renderTemplateOutput(result, "Template run launch complete.");
            await refresh();
          }, true);
        },
      },
      {
        label: "Share",
        kind: "secondary",
        onClick: async () => {
          await runAction(`Sharing template ${template.name}`, async () => {
            const result = await coreRequest("POST", `/agents/templates/${encodeURIComponent(template.template_id)}/share`, {
              shared: true,
              rotate: false,
            });
            renderTemplateOutput(result, "Template share metadata ready.");
            const shareUrl = result?.share?.share_url || result?.share?.share_uri || result?.share?.share_path;
            if (shareUrl && navigator.clipboard?.writeText) {
              try {
                await navigator.clipboard.writeText(String(shareUrl));
              } catch {
                // clipboard failure is non-fatal
              }
            }
            await refreshTemplates();
          }, false);
        },
      },
    ],
    "No local templates yet.",
  );
}

function renderTemplateGallery(payload) {
  renderTemplateCards(
    templateGalleryEl,
    payload?.templates || [],
    (template) => [
      {
        label: "Import",
        kind: "secondary",
        onClick: async () => {
          await runAction(`Importing gallery template ${template.name}`, async () => {
            const result = await coreRequest("POST", "/agents/templates/import", {
              manifest: template,
              source: "gallery",
            });
            renderTemplateOutput(result, "Gallery template imported.");
            templateManifestInput.value = JSON.stringify(result?.manifest || template, null, 2);
            saveConfig();
            await refreshTemplates();
          }, false);
        },
      },
      {
        label: "Use Objective",
        kind: "secondary",
        onClick: async () => {
          objectiveInput.value = String(template?.objective || "");
          strategySelect.value = String(template?.strategy || "single");
          candidatesInput.value = Array.isArray(template?.candidates) ? template.candidates.join(",") : "";
          saveConfig();
          setTemplateStatus(`Loaded ${template.name} into the objective console`, "ok");
        },
      },
    ],
    "No gallery templates matched the current tag filter.",
  );
}

async function refreshTemplates() {
  saveConfig();
  const query = templateTagQuery();
  const [library, gallery] = await Promise.all([
    coreRequest("GET", `/agents/templates?limit=24${query ? `&${query.slice(1)}` : ""}`),
    coreRequest("GET", `/agents/gallery${query}`),
  ]);
  renderTemplateLibrary(library);
  renderTemplateGallery(gallery);
  setTemplateStatus(
    `Templates ${Number(library?.count || 0)} local • ${Number(gallery?.count || 0)} gallery`,
    "ok",
  );
  return { library, gallery };
}

async function exportCurrentTemplate() {
  const objective = String(objectiveInput?.value || "").trim();
  if (!objective) throw new Error("Objective is required before exporting a template");
  const name = (window.prompt("Template name", objective.slice(0, 60)) || "").trim();
  if (!name) return null;
  const description = (window.prompt("Template description", `Exported operator template for ${name}`) || "").trim();
  const tags = (window.prompt("Template tags (CSV)", String(templateTagInput?.value || "").trim()) || "").trim();
  const result = await coreRequest("POST", "/agents/templates/export", {
    name,
    description,
    objective,
    strategy: String(strategySelect?.value || "single"),
    candidates: parseCandidates(candidatesInput?.value || ""),
    tags: parseCandidates(tags),
    metadata: {
      source: "desktop-tauri",
      exported_at: new Date().toISOString(),
    },
    include_memory: true,
    source: "desktop",
  });
  renderTemplateOutput(result, "Template exported.");
  templateManifestInput.value = JSON.stringify(result?.manifest || {}, null, 2);
  saveConfig();
  await refreshTemplates();
  return result;
}

async function importTemplateManifest() {
  const raw = String(templateManifestInput?.value || "").trim();
  if (!raw) throw new Error("Paste a template manifest JSON payload first");
  let manifest;
  try {
    manifest = JSON.parse(raw);
  } catch {
    throw new Error("Template manifest must be valid JSON");
  }
  const result = await coreRequest("POST", "/agents/templates/import", { manifest });
  renderTemplateOutput(result, "Template imported.");
  await refreshTemplates();
  return result;
}

function renderSummary(data) {
  const plans = Array.isArray(data?.plans) ? data.plans : [];
  const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
  const events = Array.isArray(data?.events) ? data.events : [];
  const control = data?.control || {};

  const out = {
    health: data?.health,
    models_count: data?.models_count,
    pending_plans: plans.filter((item) => String(item.status || "").toLowerCase() === "pending").length,
    active_jobs: jobs.filter((item) => ["queued", "running"].includes(String(item.status || "").toLowerCase()))
      .length,
    governance: data?.governance || {},
    events_loaded: events.length,
    mqtt_status: control.mqtt || {},
    metrics: data?.metrics || {},
  };
  summaryEl.textContent = JSON.stringify(out, null, 2);
}

function render(data) {
  renderPlans(data?.plans || []);
  renderJobs(data?.jobs || []);
  const events = data?.events || [];
  renderEvents(events);
  renderControlArtifacts(data?.control_artifacts || data?.control?.artifacts || []);
  renderGovernance(data?.governance || {});
  renderSummary(data || {});
  liveState.lastAuditId = extractMaxAuditId(events);
}

async function refresh() {
  if (refreshInFlight) {
    queuedRefresh = true;
    return;
  }
  saveConfig();
  refreshInFlight = true;
  try {
    const data = await dashboardData();
    render(data);
    setConnectionStatus("Connected", "ok");
  } catch (error) {
    setConnectionStatus("Connection failed", "error");
    throw error;
  } finally {
    refreshInFlight = false;
    if (queuedRefresh) {
      queuedRefresh = false;
      window.setTimeout(() => {
        refresh().catch((err) => {
          setActionStatus("Refresh failed", "error");
          summaryEl.textContent = String(err?.message || err);
        });
      }, 25);
    }
  }
}

async function testConnection() {
  await coreRequest("GET", "/health");
  setConnectionStatus("Connected", "ok");
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

async function pollLiveEvents() {
  if (!liveState.enabled) return;
  try {
    const query = new URLSearchParams();
    query.set("limit", "25");
    if (liveState.lastAuditId > 0) {
      query.set("since_id", String(liveState.lastAuditId));
    }
    const events = await coreRequest("GET", `/events?${query.toString()}`);
    const items = Array.isArray(events) ? events : [];
    liveState.connected = true;
    liveState.consecutiveErrors = 0;
    if (items.length > 0) {
      liveState.lastAuditId = extractMaxAuditId(items);
      const latest = items[items.length - 1] || {};
      const category = String(latest?.category || "audit");
      const action = String(latest?.action || "update");
      setLiveStatus(`Live • ${items.length} event${items.length === 1 ? "" : "s"} • ${category}:${action}`, "ok");
      scheduleRefresh(80);
    } else {
      setLiveStatus("Live • watching audit feed", "ok");
    }
  } catch (error) {
    liveState.connected = false;
    liveState.consecutiveErrors += 1;
    const backoff = Math.min(4000, 750 + (liveState.consecutiveErrors - 1) * 500);
    setLiveStatus(`Live reconnecting • ${String(error?.message || error)}`, "error");
    if (liveRefreshTimer) window.clearTimeout(liveRefreshTimer);
    liveRefreshTimer = window.setTimeout(() => {
      liveRefreshTimer = null;
      pollLiveEvents().catch(() => {});
    }, backoff);
    return;
  }
  if (!liveState.enabled) return;
  if (liveRefreshTimer) window.clearTimeout(liveRefreshTimer);
  liveRefreshTimer = window.setTimeout(() => {
    liveRefreshTimer = null;
    pollLiveEvents().catch(() => {});
  }, 750);
}

function stopLivePolling() {
  liveState.connected = false;
  if (liveRefreshTimer) {
    window.clearTimeout(liveRefreshTimer);
    liveRefreshTimer = null;
  }
}

function syncLivePolling() {
  updateLiveButton();
  saveConfig();
  if (!liveState.enabled) {
    stopLivePolling();
    setLiveStatus("Live idle", "neutral");
    return;
  }
  stopLivePolling();
  setLiveStatus("Live starting", "neutral");
  pollLiveEvents().catch((err) => {
    setLiveStatus(String(err?.message || err), "error");
  });
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
testConnectionBtn.addEventListener("click", () => {
  runAction("Testing connection", () => testConnection(), false).catch(() => {});
});
runAsyncBtn.addEventListener("click", () => {
  runAction("Queueing objective", () => queueRun(), true).catch(() => {});
});
createPlanBtn.addEventListener("click", () => {
  runAction("Creating plan", () => createPlan(), true).catch(() => {});
});
baseUrlInput.addEventListener("change", () => {
  try {
    baseUrlInput.value = normalizeBaseUrl(baseUrlInput.value || DEFAULT_BASE_URL);
    setConnectionStatus("Not connected", "neutral");
    saveConfig();
  } catch (err) {
    setConnectionStatus("Invalid base URL", "error");
    summaryEl.textContent = String(err?.message || err);
  }
});
tokenInput.addEventListener("change", saveConfig);
rememberTokenInput.addEventListener("change", saveConfig);
objectiveInput.addEventListener("change", saveConfig);
strategySelect.addEventListener("change", saveConfig);
candidatesInput.addEventListener("change", saveConfig);
executeToggle.addEventListener("change", saveConfig);
autoRepairAttemptsInput?.addEventListener("change", saveConfig);
repairStrategySelect?.addEventListener("change", saveConfig);
repairModelInput?.addEventListener("change", saveConfig);
repairCandidatesInput?.addEventListener("change", saveConfig);
repairFallbacksInput?.addEventListener("change", saveConfig);
budgetLimitInput?.addEventListener("change", saveConfig);
maxActiveRunsInput?.addEventListener("change", saveConfig);
entityDomainInput?.addEventListener("change", saveConfig);
entityPrefixInput?.addEventListener("change", saveConfig);
mqttTopicInput?.addEventListener("change", saveConfig);
mqttPayloadInput?.addEventListener("change", saveConfig);
mqttRetainInput?.addEventListener("change", saveConfig);
templateTagInput?.addEventListener("change", saveConfig);
templateManifestInput?.addEventListener("change", saveConfig);
autoRefreshInput.addEventListener("change", () => {
  saveConfig();
  startAutoRefresh();
});
liveStreamBtn?.addEventListener("click", () => {
  liveState.enabled = !liveState.enabled;
  syncLivePolling();
});
refreshEntitiesBtn?.addEventListener("click", () => {
  runAction("Refreshing IoT entities", () => refreshIoTEntities(), false).catch(() => {});
});
refreshGovernanceBtn?.addEventListener("click", () => {
  runAction("Refreshing runtime governance", () => refreshGovernance(), false).catch(() => {});
});
applyGovernanceBtn?.addEventListener("click", () => {
  runAction("Applying runtime limits", () => applyGovernanceLimits(), false).catch(() => {});
});
pauseRuntimeBtn?.addEventListener("click", () => {
  runAction("Pausing runtime", () => pauseRuntime(), false).catch(() => {});
});
resumeRuntimeBtn?.addEventListener("click", () => {
  runAction("Resuming runtime", () => resumeRuntime(), false).catch(() => {});
});
resetUsageBtn?.addEventListener("click", () => {
  runAction("Resetting governance usage", () => resetGovernanceUsage(), false).catch(() => {});
});
cancelAllJobsBtn?.addEventListener("click", () => {
  runAction("Canceling all jobs", () => cancelAllJobs(), true).catch(() => {});
});
refreshMqttStatusBtn?.addEventListener("click", () => {
  runAction("Refreshing MQTT status", () => refreshMQTTStatus(), false).catch(() => {});
});
mqttPublishBtn?.addEventListener("click", () => {
  runAction("Publishing MQTT message", () => publishMQTT(), false).catch(() => {});
});
mqttSubscribeBtn?.addEventListener("click", () => {
  runAction("Subscribing to MQTT snapshot", () => subscribeMQTTSnapshot(), false).catch(() => {});
});
refreshTemplatesBtn?.addEventListener("click", () => {
  runAction("Refreshing templates", () => refreshTemplates(), false).catch(() => {});
});
exportTemplateBtn?.addEventListener("click", () => {
  runAction("Exporting template", () => exportCurrentTemplate(), false).catch(() => {});
});
importTemplateBtn?.addEventListener("click", () => {
  runAction("Importing template manifest", () => importTemplateManifest(), false).catch(() => {});
});

loadConfig();
setActionStatus("Idle", "neutral");
setConnectionStatus("Not connected", "neutral");
updateLiveButton();
setLiveStatus(liveState.enabled ? "Live waiting for first event" : "Live idle", "neutral");
setGovernanceStatus("Unknown", "neutral");
setIoTStatus("Idle", "neutral");
setTemplateStatus("Idle", "neutral");
renderMQTTOutput(null);
renderTemplateOutput(null);
refresh()
  .catch((err) => {
    setActionStatus("Initial refresh failed", "error");
    summaryEl.textContent = String(err?.message || err);
  })
  .finally(() => {
    refreshGovernance().catch(() => {});
    refreshMQTTStatus().catch(() => {});
    refreshTemplates().catch(() => {});
    startAutoRefresh();
    syncLivePolling();
  });

window.addEventListener("beforeunload", () => {
  if (refreshTimer) window.clearInterval(refreshTimer);
  if (scheduledRefreshTimer) window.clearTimeout(scheduledRefreshTimer);
  stopLivePolling();
});
