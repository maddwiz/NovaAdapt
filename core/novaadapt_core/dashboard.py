from __future__ import annotations


def render_dashboard_html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>NovaAdapt Core Dashboard</title>
  <style>
    :root {
      --bg: #0d1117;
      --panel: #161b22;
      --muted: #8b949e;
      --text: #e6edf3;
      --accent: #2f81f7;
      --ok: #3fb950;
      --warn: #d29922;
      --bad: #f85149;
      --border: #30363d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: radial-gradient(1000px 500px at 20% -10%, #1f2a44, var(--bg));
      color: var(--text);
      min-height: 100vh;
    }
    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      padding: 20px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      font-weight: 700;
    }
    .sub { color: var(--muted); margin-bottom: 18px; }
    .grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }
    .card {
      background: color-mix(in oklab, var(--panel), #000 8%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px;
    }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
    .value { font-size: 20px; margin-top: 4px; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .toolbar { margin: 14px 0; display: flex; gap: 8px; flex-wrap: wrap; }
    .operator-panel { margin-bottom: 12px; }
    .governance-panel { margin-bottom: 12px; }
    .control-grid {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    .control-grid .full { grid-column: 1 / -1; }
    .control-field label {
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    .control-field input,
    .control-field select,
    .control-field textarea {
      width: 100%;
      border: 1px solid var(--border);
      background: #0f141b;
      color: var(--text);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
    }
    .control-field textarea {
      min-height: 92px;
      resize: vertical;
    }
    .control-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .control-status {
      min-height: 18px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .control-status.ok { color: var(--ok); }
    .control-status.bad { color: var(--bad); }
    .obs-grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      margin-bottom: 12px;
    }
    .obs-list {
      display: grid;
      gap: 6px;
    }
    .obs-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
    }
    .obs-row .mono {
      color: var(--muted);
      min-width: 92px;
    }
    .obs-pills {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .obs-pill {
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #0f141b;
    }
    button {
      border: 1px solid var(--border);
      background: #21262d;
      color: var(--text);
      padding: 8px 12px;
      border-radius: 8px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    button.mini {
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 12px;
      margin-right: 6px;
    }
    button.warn {
      border-color: color-mix(in oklab, var(--bad), #000 35%);
      color: var(--bad);
    }
    .action-status {
      min-height: 18px;
      margin: 4px 0 10px;
      color: var(--muted);
      font-size: 13px;
    }
    .action-status.ok { color: var(--ok); }
    .action-status.bad { color: var(--bad); }
    .tables {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    }
    .artifact-list {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      margin-top: 12px;
    }
    .artifact {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
    }
    .artifact-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .artifact-media {
      width: 100%;
      max-height: 200px;
      object-fit: cover;
      border-radius: 10px;
      border: 1px solid var(--border);
      margin-bottom: 8px;
      background: #0b0f14;
    }
    .artifact-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin: 6px 0 0;
      white-space: pre-wrap;
    }
    table {
      width: 100%; border-collapse: collapse;
      background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
    }
    .section-title {
      font-size: 14px;
      color: var(--muted);
      margin: 0 0 6px;
      letter-spacing: .03em;
      text-transform: uppercase;
    }
    th, td {
      text-align: left; padding: 10px; border-bottom: 1px solid var(--border); font-size: 13px;
    }
    th { color: var(--muted); font-weight: 600; }
    tr:last-child td { border-bottom: none; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .detail {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      margin-top: 4px;
      white-space: pre-wrap;
      word-break: break-word;
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>NovaAdapt Core Dashboard</h1>
    <div class=\"sub\">Live operational view with one-click controls for plans, jobs, and audit events.</div>

    <div class=\"grid\" id=\"summary\"></div>

    <div class=\"toolbar\">
      <button id=\"refresh\">Refresh</button>
      <button id=\"auto\">Auto: Off</button>
      <button id=\"live\">Live: Off</button>
    </div>
    <div class=\"action-status\" id=\"action-status\"></div>

    <div class=\"card operator-panel\">
      <div class=\"section-title\">Operator Console</div>
      <div class=\"control-grid\">
        <div class=\"control-field full\">
          <label for=\"operator-objective\">Objective</label>
          <textarea id=\"operator-objective\" placeholder=\"Describe the run or plan you want NovaAdapt to execute.\"></textarea>
        </div>
        <div class=\"control-field\">
          <label for=\"operator-strategy\">Strategy</label>
          <select id=\"operator-strategy\">
            <option value=\"single\">single</option>
            <option value=\"vote\">vote</option>
            <option value=\"decompose\">decompose</option>
          </select>
        </div>
        <div class=\"control-field\">
          <label for=\"operator-model\">Model</label>
          <input id=\"operator-model\" placeholder=\"default model\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-candidates\">Candidates</label>
          <input id=\"operator-candidates\" placeholder=\"model-a, model-b\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-fallbacks\">Fallbacks</label>
          <input id=\"operator-fallbacks\" placeholder=\"model-c, model-d\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-execute\">Run Mode</label>
          <select id=\"operator-execute\">
            <option value=\"true\">execute</option>
            <option value=\"false\">preview</option>
          </select>
        </div>
        <div class=\"control-field\">
          <label for=\"operator-allow-dangerous\">Dangerous Actions</label>
          <select id=\"operator-allow-dangerous\">
            <option value=\"false\">block</option>
            <option value=\"true\">allow</option>
          </select>
        </div>
        <div class=\"control-field\">
          <label for=\"operator-max-actions\">Max Actions</label>
          <input id=\"operator-max-actions\" type=\"number\" min=\"1\" value=\"25\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-action-retries\">Action Retries</label>
          <input id=\"operator-action-retries\" type=\"number\" min=\"0\" value=\"2\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-action-backoff\">Retry Backoff Seconds</label>
          <input id=\"operator-action-backoff\" type=\"number\" min=\"0\" step=\"0.1\" value=\"0.2\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-auto-repair\">Auto Repair Attempts</label>
          <input id=\"operator-auto-repair\" type=\"number\" min=\"0\" value=\"1\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-repair-strategy\">Repair Strategy</label>
          <select id=\"operator-repair-strategy\">
            <option value=\"single\">single</option>
            <option value=\"vote\">vote</option>
            <option value=\"decompose\">decompose</option>
          </select>
        </div>
        <div class=\"control-field\">
          <label for=\"operator-repair-model\">Repair Model</label>
          <input id=\"operator-repair-model\" placeholder=\"default repair model\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-repair-candidates\">Repair Candidates</label>
          <input id=\"operator-repair-candidates\" placeholder=\"model-a, model-b\" />
        </div>
        <div class=\"control-field\">
          <label for=\"operator-repair-fallbacks\">Repair Fallbacks</label>
          <input id=\"operator-repair-fallbacks\" placeholder=\"model-c, model-d\" />
        </div>
      </div>
      <div class=\"control-actions\">
        <button id=\"run-async\">Run Async</button>
        <button id=\"create-plan\">Create Plan</button>
      </div>
    </div>

    <div class=\"card governance-panel\">
      <div class=\"section-title\">Runtime Governance</div>
      <div class=\"control-grid\">
        <div class=\"control-field\">
          <label for=\"governance-paused\">Paused</label>
          <select id=\"governance-paused\">
            <option value=\"false\">running</option>
            <option value=\"true\">paused</option>
          </select>
        </div>
        <div class=\"control-field\">
          <label for=\"governance-pause-reason\">Pause Reason</label>
          <input id=\"governance-pause-reason\" placeholder=\"ops freeze\" />
        </div>
        <div class=\"control-field\">
          <label for=\"governance-budget-limit\">Budget Limit USD</label>
          <input id=\"governance-budget-limit\" type=\"number\" min=\"0\" step=\"0.01\" placeholder=\"unlimited\" />
        </div>
        <div class=\"control-field\">
          <label for=\"governance-max-runs\">Max Active Runs</label>
          <input id=\"governance-max-runs\" type=\"number\" min=\"1\" placeholder=\"unlimited\" />
        </div>
      </div>
      <div class=\"control-actions\">
        <button id=\"apply-governance\">Apply Governance</button>
        <button id=\"toggle-pause\">Pause Runtime</button>
        <button id=\"reset-usage\">Reset Usage</button>
        <button id=\"cancel-all-jobs\" class=\"warn\">Cancel All Jobs</button>
      </div>
      <div class=\"control-status\" id=\"governance-status\"></div>
    </div>

    <div class=\"obs-grid\" id=\"observability\"></div>

    <div class=\"tables\">
      <div>
        <div class=\"section-title\">Async Jobs</div>
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Status / Kind</th>
              <th>Objective / Summary</th>
              <th>Created</th>
              <th>Finished</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id=\"jobs\"></tbody>
        </table>
      </div>
      <div>
        <div class=\"section-title\">Approval Plans</div>
        <table>
          <thead>
            <tr>
              <th>Plan ID</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Objective / Summary</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id=\"plans\"></tbody>
        </table>
      </div>
      <div>
        <div class=\"section-title\">Audit Events</div>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Category</th>
              <th>Action</th>
              <th>Status</th>
              <th>Entity</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody id=\"events\"></tbody>
        </table>
      </div>
    </div>

    <div>
      <div class=\"section-title\">Control Artifacts</div>
      <div id=\"artifacts\" class=\"artifact-list\"></div>
    </div>
  </div>

  <script>
    const state = {
      auto: false,
      timer: null,
      live: false,
      eventSource: null,
      lastAuditId: 0,
      refreshScheduled: null,
      refreshInFlight: false,
    };
    const authToken = new URLSearchParams(window.location.search).get('token');
    const actionStatus = document.getElementById('action-status');
    const governanceStatus = document.getElementById('governance-status');
    const jobsTbody = document.getElementById('jobs');
    const plansTbody = document.getElementById('plans');
    const artifactsEl = document.getElementById('artifacts');
    const observabilityEl = document.getElementById('observability');
    const operatorObjective = document.getElementById('operator-objective');
    const runAsyncButton = document.getElementById('run-async');
    const createPlanButton = document.getElementById('create-plan');
    const liveButton = document.getElementById('live');
    const applyGovernanceButton = document.getElementById('apply-governance');
    const togglePauseButton = document.getElementById('toggle-pause');
    const resetUsageButton = document.getElementById('reset-usage');
    const cancelAllJobsButton = document.getElementById('cancel-all-jobs');

    function metricColor(v, ok=0){
      if (Number(v) <= ok) return 'ok';
      if (Number(v) <= ok + 5) return 'warn';
      return 'bad';
    }

    function withToken(path){
      if (!authToken) return path;
      const sep = path.includes('?') ? '&' : '?';
      return `${path}${sep}token=${encodeURIComponent(authToken)}`;
    }

    function authHeaders(includeJSON=false){
      const headers = {};
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      if (includeJSON) headers['Content-Type'] = 'application/json';
      return headers;
    }

    function setActionStatus(message, ok=true){
      actionStatus.textContent = String(message || '');
      actionStatus.className = `action-status ${ok ? 'ok' : 'bad'}`;
    }

    function setGovernanceStatus(message, ok=true){
      governanceStatus.textContent = String(message || '');
      governanceStatus.className = `control-status ${ok ? 'ok' : 'bad'}`;
    }

    function escapeHTML(value){
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function parseNameList(value){
      return String(value || '')
        .split(',')
        .map(item => item.trim())
        .filter(Boolean);
    }

    function formatMoney(value){
      const amount = Number(value || 0);
      return `$${amount.toFixed(4)}`;
    }

    function readInteger(id, fallback){
      const value = Number.parseInt(document.getElementById(id).value, 10);
      return Number.isFinite(value) ? value : fallback;
    }

    function readFloat(id, fallback){
      const value = Number.parseFloat(document.getElementById(id).value);
      return Number.isFinite(value) ? value : fallback;
    }

    function syncControlValue(id, value){
      const element = document.getElementById(id);
      if (!element) return;
      if (document.activeElement === element) return;
      const normalized = value == null ? '' : String(value);
      if (element.value !== normalized) {
        element.value = normalized;
      }
    }

    function operatorControlPayload(includeObjective=true){
      const payload = {
        strategy: document.getElementById('operator-strategy').value || 'single',
        allow_dangerous: document.getElementById('operator-allow-dangerous').value === 'true',
        max_actions: Math.max(1, readInteger('operator-max-actions', 25)),
        action_retry_attempts: Math.max(0, readInteger('operator-action-retries', 2)),
        action_retry_backoff_seconds: Math.max(0, readFloat('operator-action-backoff', 0.2)),
        auto_repair_attempts: Math.max(0, readInteger('operator-auto-repair', 1)),
        repair_strategy: document.getElementById('operator-repair-strategy').value || 'single',
      };
      const model = document.getElementById('operator-model').value.trim();
      const candidates = parseNameList(document.getElementById('operator-candidates').value);
      const fallbacks = parseNameList(document.getElementById('operator-fallbacks').value);
      const repairModel = document.getElementById('operator-repair-model').value.trim();
      const repairCandidates = parseNameList(document.getElementById('operator-repair-candidates').value);
      const repairFallbacks = parseNameList(document.getElementById('operator-repair-fallbacks').value);
      if (includeObjective) {
        payload.objective = operatorObjective.value.trim();
      }
      if (model) payload.model = model;
      if (candidates.length) payload.candidates = candidates;
      if (fallbacks.length) payload.fallbacks = fallbacks;
      if (repairModel) payload.repair_model = repairModel;
      if (repairCandidates.length) payload.repair_candidates = repairCandidates;
      if (repairFallbacks.length) payload.repair_fallbacks = repairFallbacks;
      return payload;
    }

    function operatorExecutionPayload(){
      return {
        ...operatorControlPayload(false),
        execute: true,
      };
    }

    function governancePayload(options={}){
      const pausedValue = document.getElementById('governance-paused').value === 'true';
      const pauseReason = document.getElementById('governance-pause-reason').value.trim();
      const budgetRaw = document.getElementById('governance-budget-limit').value.trim();
      const maxRunsRaw = document.getElementById('governance-max-runs').value.trim();
      const payload = {};
      if (options.includePaused !== false) payload.paused = pausedValue;
      if (options.includePauseReason !== false) payload.pause_reason = pauseReason;
      if (options.includeBudget !== false) {
        payload.budget_limit_usd = budgetRaw === '' ? null : Math.max(0, Number.parseFloat(budgetRaw) || 0);
      }
      if (options.includeMaxRuns !== false) {
        payload.max_active_runs = maxRunsRaw === '' ? null : Math.max(1, Number.parseInt(maxRunsRaw, 10) || 1);
      }
      if (options.resetUsage) payload.reset_usage = true;
      return payload;
    }

    function countResultsByStatus(results){
      const counts = {};
      for (const item of Array.isArray(results) ? results : []) {
        const status = String(item?.status || 'unknown').toLowerCase();
        counts[status] = (counts[status] || 0) + 1;
      }
      return counts;
    }

    function summarizeRepair(repair, results){
      const counts = countResultsByStatus(results);
      const repairedCount = Number(counts.repaired || 0);
      if (!repair || typeof repair !== 'object') {
        return repairedCount > 0 ? `${repairedCount} repaired action${repairedCount === 1 ? '' : 's'}` : '';
      }
      const attempts = Number(repair.attempts || 0);
      const unresolved = Array.isArray(repair.failed_indexes) ? repair.failed_indexes.length : 0;
      const healed = Boolean(repair.healed);
      const parts = [];
      if (healed) parts.push('auto-repair healed');
      else if (attempts > 0) parts.push('auto-repair attempted');
      if (repairedCount > 0) parts.push(`${repairedCount} repaired`);
      if (attempts > 0) parts.push(`${attempts} attempt${attempts === 1 ? '' : 's'}`);
      if (unresolved > 0 && !healed) parts.push(`${unresolved} unresolved`);
      if (repair.last_error && !healed) parts.push(String(repair.last_error));
      return parts.join(' • ');
    }

    function summarizeCollaboration(voteSummary, collaboration, fallbackStrategy){
      const vote = voteSummary && typeof voteSummary === 'object' ? voteSummary : {};
      const collab = collaboration && typeof collaboration === 'object' ? collaboration : {};
      const mode = String(collab.mode || fallbackStrategy || '').toLowerCase();
      if (vote.subtasks_total !== undefined || mode === 'decompose') {
        const total = Number(vote.subtasks_total || 0);
        const succeeded = Number(vote.subtasks_succeeded || 0);
        const reviewed = Number(vote.reviewed_subtasks || 0);
        const batches = Number(vote.parallel_batches || 0);
        const parts = ['decompose'];
        if (total > 0) parts.push(`${succeeded}/${total} subtasks`);
        if (reviewed > 0) parts.push(`${reviewed} reviewed`);
        if (batches > 0) parts.push(`${batches} batches`);
        if (vote.reason) parts.push(String(vote.reason).replaceAll('_', ' '));
        return parts.join(' • ');
      }
      if (vote.winner_votes !== undefined || mode === 'vote') {
        const winnerVotes = Number(vote.winner_votes || 0);
        const totalVotes = Number(vote.total_votes || 0);
        const parts = ['vote'];
        if (totalVotes > 0) parts.push(`${winnerVotes}/${totalVotes} votes`);
        if (vote.quorum_met) parts.push('quorum');
        return parts.join(' • ');
      }
      return '';
    }

    function transcriptPreviewLines(collaboration, limit=3){
      const collab = collaboration && typeof collaboration === 'object' ? collaboration : {};
      const transcript = Array.isArray(collab.transcript) ? collab.transcript : [];
      return transcript.map(item => {
        const type = String(item?.type || '').toLowerCase();
        if (type === 'subtask_started') {
          const subtaskId = String(item?.subtask_id || 'subtask');
          const model = String(item?.model || '');
          return `started ${subtaskId}${model ? ` with ${model}` : ''}`;
        }
        if (type === 'subtask_output') {
          const subtaskId = String(item?.subtask_id || 'subtask');
          const model = String(item?.model || 'model');
          const attempt = Number(item?.attempt || 1);
          return `output ${subtaskId} • ${model} • attempt ${attempt}`;
        }
        if (type === 'subtask_review') {
          const reviewer = String(item?.reviewer_model || 'reviewer');
          const subtaskId = String(item?.subtask_id || 'subtask');
          return `${reviewer} ${item?.approved ? 'approved' : 'rejected'} ${subtaskId}`;
        }
        if (type === 'subtask_failed') {
          const subtaskId = String(item?.subtask_id || 'subtask');
          const error = String(item?.error || 'failed');
          return `${subtaskId} failed • ${error}`;
        }
        if (type === 'synthesis') {
          return `synthesis by ${String(item?.model || 'model')}`;
        }
        return '';
      }).filter(Boolean).slice(0, limit);
    }

    function summarizeJobResult(result, fallbackKind='run'){
      const payload = result && typeof result === 'object' ? result : null;
      if (!payload) return '';
      const counts = countResultsByStatus(payload.results);
      const parts = [];
      const strategy = String(payload.strategy || '');
      const model = String(payload.model || '');
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
      return parts.join(' • ');
    }

    function renderObservability(observability){
      const payload = observability && typeof observability === 'object' ? observability : {};
      const runtime = payload.runtime && typeof payload.runtime === 'object' ? payload.runtime : {};
      const repairs = payload.repairs && typeof payload.repairs === 'object' ? payload.repairs : {};
      const collaboration = payload.collaboration && typeof payload.collaboration === 'object' ? payload.collaboration : {};
      const events = payload.events && typeof payload.events === 'object' ? payload.events : {};
      const runtimeTotals = runtime.totals && typeof runtime.totals === 'object' ? runtime.totals : {};
      const runtimeRecent = runtime.recent && typeof runtime.recent === 'object' ? runtime.recent : {};
      const perModel = Array.isArray(runtime.per_model) ? runtime.per_model : [];
      const runtimeTimeline = Array.isArray(runtime.timeline) ? runtime.timeline : [];
      const repairTimeline = Array.isArray(repairs.timeline) ? repairs.timeline : [];
      const collaborationTimeline = Array.isArray(collaboration.timeline) ? collaboration.timeline : [];
      const repairDomains = Array.isArray(repairs.domains) ? repairs.domains : [];
      const eventCategories = Array.isArray(events.categories) ? events.categories : [];
      const failureCategories = Array.isArray(events.failure_categories) ? events.failure_categories : [];

      function rows(items, formatter){
        return `<div class="obs-list">${items.map(item => formatter(item)).join('')}</div>`;
      }

      function timelineRows(items, formatter){
        if (!items.length) return '<div class="detail">No recent timeline data</div>';
        return rows(items, formatter);
      }

      observabilityEl.innerHTML = `
        <div class="card">
          <div class="section-title">Runtime Trends</div>
          ${rows([
            ['Runs total', runtimeTotals.runs_total ?? 0],
            ['LLM calls', runtimeTotals.llm_calls_total ?? 0],
            ['Spend', formatMoney(runtimeTotals.spend_estimate_usd ?? 0)],
            ['Active runs', runtimeTotals.active_runs ?? 0],
            ['Recent runs', runtimeRecent.runs ?? 0],
            ['Recent failures', runtimeRecent.failed_runs ?? 0],
          ], ([label, value]) => `<div class="obs-row"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`)}
          <div class="detail">${escapeHTML(runtimeTotals.paused ? `Paused: ${runtimeTotals.pause_reason || 'operator pause'}` : `Last strategy: ${runtimeTotals.last_strategy || 'n/a'}`)}</div>
          <div class="detail">Per-model usage</div>
          ${perModel.length ? rows(perModel.slice(0, 5), item => `
            <div class="obs-row">
              <span>${escapeHTML(item.name || 'model')}</span>
              <span class="mono">${escapeHTML(`${item.calls || 0} calls • ${formatMoney(item.estimated_cost_usd || 0)}`)}</span>
            </div>
          `) : '<div class="detail">No per-model usage yet</div>'}
          <div class="detail">Recent runtime timeline</div>
          ${timelineRows(runtimeTimeline, item => `
            <div class="obs-row">
              <span>${escapeHTML(item.bucket || 'unknown')}</span>
              <span class="mono">${escapeHTML(`${item.runs || 0} runs • ${item.llm_calls || 0} calls • ${formatMoney(item.estimated_cost_usd || 0)}`)}</span>
            </div>
          `)}
        </div>
        <div class="card">
          <div class="section-title">Repair Activity</div>
          ${rows([
            ['Attempts', repairs.attempted ?? 0],
            ['Healed', repairs.healed ?? 0],
            ['Failed', repairs.failed ?? 0],
            ['Repaired actions', repairs.repaired_actions ?? 0],
            ['Failed actions', repairs.failed_actions ?? 0],
          ], ([label, value]) => `<div class="obs-row"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`)}
          <div class="obs-pills">
            ${(repairDomains.length ? repairDomains : [{ label: 'none', count: 0 }]).map(item => `<span class="obs-pill">${escapeHTML(`${item.label}: ${item.count}`)}</span>`).join('')}
          </div>
          <div class="detail">Repair timeline</div>
          ${timelineRows(repairTimeline, item => `
            <div class="obs-row">
              <span>${escapeHTML(item.bucket || 'unknown')}</span>
              <span class="mono">${escapeHTML(`${item.attempted || 0} attempts • ${item.healed || 0} healed • ${item.failed || 0} failed`)}</span>
            </div>
          `)}
        </div>
        <div class="card">
          <div class="section-title">Collaboration</div>
          ${rows([
            ['Decompose runs', collaboration.decompose_runs ?? 0],
            ['Vote runs', collaboration.vote_runs ?? 0],
            ['Transcript events', collaboration.transcript_events ?? 0],
            ['Review events', collaboration.review_events ?? 0],
            ['Parallel batches', collaboration.parallel_batches ?? 0],
            ['Subtasks', collaboration.subtasks_total ?? 0],
          ], ([label, value]) => `<div class="obs-row"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong></div>`)}
          <div class="detail">Collaboration timeline</div>
          ${timelineRows(collaborationTimeline, item => `
            <div class="obs-row">
              <span>${escapeHTML(item.bucket || 'unknown')}</span>
              <span class="mono">${escapeHTML(`${item.decompose_runs || 0} dec • ${item.vote_runs || 0} vote • ${item.transcript_events || 0} events`)}</span>
            </div>
          `)}
        </div>
        <div class="card">
          <div class="section-title">Failure Hotspots</div>
          <div class="detail">Event categories</div>
          ${eventCategories.length ? rows(eventCategories, item => `
            <div class="obs-row">
              <span>${escapeHTML(item.label || 'unknown')}</span>
              <span class="mono">${escapeHTML(item.count || 0)}</span>
            </div>
          `) : '<div class="detail">No event categories yet</div>'}
          <div class="detail">Failure categories</div>
          ${failureCategories.length ? rows(failureCategories, item => `
            <div class="obs-row">
              <span>${escapeHTML(item.label || 'unknown')}</span>
              <span class="mono">${escapeHTML(item.count || 0)}</span>
            </div>
          `) : '<div class="detail">No failing categories yet</div>'}
        </div>
      `;
    }

    function renderArtifacts(items){
      const artifacts = Array.isArray(items) ? items : [];
      if (!artifacts.length) {
        artifactsEl.innerHTML = '<div class=\"card\"><div class=\"label\">Artifacts</div><div class=\"value\">No control artifacts yet</div></div>';
        return;
      }
      artifactsEl.innerHTML = artifacts.slice(0, 8).map(item => {
        const preview = item.preview_available && item.preview_path
          ? `<img class=\"artifact-media\" src=\"${escapeHTML(withToken(item.preview_path))}\" alt=\"artifact preview\" loading=\"lazy\" />`
          : '';
        const heading = [item.control_type || 'control', item.platform || item.transport || item.action_type || 'preview']
          .filter(Boolean)
          .join(' / ');
        return `
          <div class=\"artifact\">
            <div class=\"artifact-head\">
              <strong>${escapeHTML(heading)}</strong>
              <span class=\"mono\">${escapeHTML(item.status || 'unknown')}</span>
            </div>
            ${preview}
            <p class=\"artifact-meta\">${escapeHTML(item.goal || item.output_preview || '(no goal)')}</p>
            <p class=\"artifact-meta\">Action: ${escapeHTML(item.action_type || 'unknown')}${item.target ? ` • ${escapeHTML(item.target)}` : ''}</p>
            <p class=\"artifact-meta\">Model: ${escapeHTML(item.model || 'n/a')}${item.model_id ? ` • ${escapeHTML(item.model_id)}` : ''}</p>
            <p class=\"artifact-meta\">${escapeHTML(item.created_at || '')}${item.dangerous ? ' • dangerous' : ''}</p>
          </div>
        `;
      }).join('');
    }

    function syncGovernanceInputs(governance){
      const payload = governance && typeof governance === 'object' ? governance : {};
      const paused = Boolean(payload.paused);
      syncControlValue('governance-paused', paused ? 'true' : 'false');
      syncControlValue('governance-pause-reason', payload.pause_reason || '');
      syncControlValue(
        'governance-budget-limit',
        payload.budget_limit_usd == null ? '' : Number(payload.budget_limit_usd).toString()
      );
      syncControlValue(
        'governance-max-runs',
        payload.max_active_runs == null ? '' : Number(payload.max_active_runs).toString()
      );
      togglePauseButton.textContent = paused ? 'Resume Runtime' : 'Pause Runtime';
    }

    function updateLiveButton(){
      liveButton.textContent = `Live: ${state.live ? 'On' : 'Off'}`;
    }

    function scheduleRefresh(delayMs=150){
      if (state.refreshScheduled) clearTimeout(state.refreshScheduled);
      state.refreshScheduled = setTimeout(() => {
        state.refreshScheduled = null;
        refresh();
      }, Math.max(0, Number(delayMs || 0)));
    }

    function closeLiveStream(){
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
    }

    function connectLiveStream(){
      closeLiveStream();
      if (!state.live) return;
      if (!authToken) {
        state.live = false;
        updateLiveButton();
        setActionStatus('Live stream requires the dashboard token in the URL query', false);
        return;
      }
      const streamUrl = withToken(`/events/stream?timeout=300&interval=0.25&since_id=${encodeURIComponent(state.lastAuditId)}`);
      try {
        const source = new EventSource(streamUrl);
        state.eventSource = source;
        source.addEventListener('audit', (event) => {
          try {
            const payload = JSON.parse(event.data || '{}');
            if (payload && payload.id != null) {
              state.lastAuditId = Math.max(state.lastAuditId, Number(payload.id || 0));
            }
            setActionStatus(`Live event • ${payload.category || 'audit'}:${payload.action || 'update'}`, true);
          } catch {
            setActionStatus('Live event received', true);
          }
          scheduleRefresh(100);
        });
        source.addEventListener('timeout', () => {
          if (!state.live) return;
          closeLiveStream();
          setTimeout(connectLiveStream, 250);
        });
        source.onerror = () => {
          if (!state.live) return;
          closeLiveStream();
          setTimeout(connectLiveStream, 1000);
        };
      } catch (err) {
        state.live = false;
        updateLiveButton();
        setActionStatus(String(err), false);
      }
    }

    function toggleLiveStream(){
      state.live = !state.live;
      updateLiveButton();
      if (state.live) {
        setActionStatus('Live stream enabled', true);
        connectLiveStream();
      } else {
        closeLiveStream();
        setActionStatus('Live stream disabled', true);
      }
    }

    async function fetchJSON(path){
      const r = await fetch(withToken(path), {
        credentials: 'same-origin',
        headers: authHeaders(false),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    }

    async function postJSON(path, body){
      const r = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: authHeaders(true),
        body: JSON.stringify(body || {}),
      });
      const text = await r.text();
      let payload = null;
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        payload = { raw: text };
      }
      if (!r.ok) {
        throw new Error(payload?.error ? `HTTP ${r.status}: ${payload.error}` : `HTTP ${r.status}`);
      }
      return payload;
    }

    async function handleOperatorAction(kind){
      const payload = operatorControlPayload(true);
      if (!payload.objective) {
        setActionStatus('Objective is required', false);
        operatorObjective.focus();
        return;
      }

      if (kind === 'run') {
        payload.execute = document.getElementById('operator-execute').value === 'true';
      }

      const button = kind === 'run' ? runAsyncButton : createPlanButton;
      button.disabled = true;
      try {
        if (kind === 'run') {
          const out = await postJSON('/run_async', payload);
          setActionStatus(`Queued objective run (job ${out.job_id || 'n/a'})`, true);
        } else {
          const out = await postJSON('/plans', payload);
          setActionStatus(`Created plan ${out.id || 'n/a'}`, true);
        }
        await refresh();
      } catch (err) {
        setActionStatus(String(err), false);
      } finally {
        button.disabled = false;
      }
    }

    async function handleGovernanceAction(kind){
      const buttonMap = {
        apply: applyGovernanceButton,
        togglePause: togglePauseButton,
        resetUsage: resetUsageButton,
        cancelAll: cancelAllJobsButton,
      };
      const button = buttonMap[kind];
      if (!button) return;
      button.disabled = true;
      try {
        if (kind === 'apply') {
          const payload = governancePayload();
          const out = await postJSON('/runtime/governance', payload);
          syncGovernanceInputs(out);
          setGovernanceStatus(`Governance updated • paused=${Boolean(out.paused)}`, true);
        } else if (kind === 'togglePause') {
          const shouldPause = document.getElementById('governance-paused').value !== 'true';
          const payload = governancePayload({
            includeBudget: false,
            includeMaxRuns: false,
          });
          payload.paused = shouldPause;
          payload.pause_reason = shouldPause
            ? (payload.pause_reason || 'Operator paused runtime')
            : '';
          const out = await postJSON('/runtime/governance', payload);
          syncGovernanceInputs(out);
          setGovernanceStatus(shouldPause ? 'Runtime paused' : 'Runtime resumed', true);
        } else if (kind === 'resetUsage') {
          const out = await postJSON('/runtime/governance', {
            reset_usage: true,
          });
          syncGovernanceInputs(out);
          setGovernanceStatus('Runtime usage counters reset', true);
        } else if (kind === 'cancelAll') {
          const pause = document.getElementById('governance-paused').value === 'true';
          const pauseReason = document.getElementById('governance-pause-reason').value.trim() || 'Runtime paused during cancel-all';
          const out = await postJSON('/runtime/jobs/cancel_all', {
            pause,
            pause_reason: pauseReason,
          });
          if (out.governance) {
            syncGovernanceInputs(out.governance);
          }
          setGovernanceStatus(`Cancel-all requested • canceled=${out.canceled ?? out.ok ?? true}`, true);
        }
        await refresh();
      } catch (err) {
        setGovernanceStatus(String(err), false);
      } finally {
        button.disabled = false;
      }
    }

    async function handleTableAction(event){
      const button = event.target.closest('button[data-action]');
      if (!button) return;

      const action = button.dataset.action;
      const id = button.dataset.id;
      if (!id) return;
      button.disabled = true;

      try {
        if (action === 'cancel-job') {
          await postJSON(`/jobs/${encodeURIComponent(id)}/cancel`, {});
          setActionStatus(`Requested cancel for job ${id}`, true);
        } else if (action === 'approve-plan') {
          const out = await postJSON(`/plans/${encodeURIComponent(id)}/approve_async`, operatorExecutionPayload());
          setActionStatus(`Queued approval for plan ${id} (job ${out.job_id || 'n/a'})`, true);
        } else if (action === 'reject-plan') {
          const reason = prompt(`Reject plan ${id}. Optional reason:`, 'Operator rejected');
          await postJSON(`/plans/${encodeURIComponent(id)}/reject`, reason ? { reason } : {});
          setActionStatus(`Rejected plan ${id}`, true);
        } else if (action === 'undo-plan') {
          await postJSON(`/plans/${encodeURIComponent(id)}/undo`, { mark_only: true });
          setActionStatus(`Marked plan ${id} action logs as undone`, true);
        } else if (action === 'retry-failed-plan') {
          const out = await postJSON(`/plans/${encodeURIComponent(id)}/retry_failed_async`, operatorExecutionPayload());
          setActionStatus(`Queued failed-action retry for plan ${id} (job ${out.job_id || 'n/a'})`, true);
        }
        await refresh();
      } catch (err) {
        setActionStatus(String(err), false);
      } finally {
        button.disabled = false;
      }
    }

    async function refresh(){
      if (state.refreshInFlight) return;
      state.refreshInFlight = true;
      try {
        const data = await fetchJSON('/dashboard/data?jobs_limit=25&plans_limit=25&events_limit=25');
        const health = data.health || {};
        const jobs = data.jobs || [];
        const plans = data.plans || [];
        const events = data.events || [];
        const metrics = data.metrics || {};
        const observability = data.observability || {};
        const modelsCount = Number(data.models_count || 0);
        const control = data.control || {};
        const controlArtifacts = data.control_artifacts || control.artifacts || [];
        const governance = data.governance || {};
        const browser = control.browser || {};
        const mobile = control.mobile || {};
        const homeassistant = control.homeassistant || {};
        const mqtt = control.mqtt || {};
        const pendingPlans = plans.filter(item => item.status === 'pending').length;
        const runningJobs = jobs.filter(item => item.status === 'running').length;
        const failedAudits = events.filter(item => item.status === 'error' || item.status === 'failed').length;
        const auditIds = events.map(item => Number(item?.id || 0)).filter(value => Number.isFinite(value));
        if (auditIds.length) {
          state.lastAuditId = Math.max(state.lastAuditId, ...auditIds);
        }
        const mobilePlatforms = [];
        if (mobile.android) mobilePlatforms.push(`android:${mobile.android.ok ? 'ready' : 'degraded'}`);
        if (mobile.ios) mobilePlatforms.push(`ios:${mobile.ios.ok ? 'ready' : 'degraded'}`);

        const summary = [
          { label: 'Service', value: health.ok ? 'Healthy' : 'Unhealthy', cls: health.ok ? 'ok' : 'bad' },
          { label: 'Configured Models', value: modelsCount, cls: '' },
          { label: 'Browser Runtime', value: browser.ok ? 'Ready' : 'Degraded', cls: browser.ok ? 'ok' : 'warn' },
          { label: 'Mobile Runtime', value: mobilePlatforms.join(' | ') || (mobile.ok ? 'Ready' : 'Degraded'), cls: mobile.ok ? 'ok' : 'warn' },
          { label: 'IoT Runtime', value: homeassistant.ok ? 'Ready' : 'Degraded', cls: homeassistant.ok ? 'ok' : 'warn' },
          { label: 'MQTT Runtime', value: mqtt.ok ? 'Ready' : (mqtt.configured ? 'Degraded' : 'Not Configured'), cls: mqtt.ok ? 'ok' : (mqtt.configured ? 'warn' : '') },
          { label: 'Running Jobs', value: runningJobs, cls: runningJobs > 0 ? 'warn' : 'ok' },
          { label: 'Pending Plans', value: pendingPlans, cls: pendingPlans > 0 ? 'warn' : 'ok' },
          { label: 'Failed Audits', value: failedAudits, cls: metricColor(failedAudits, 0) },
          { label: 'Requests Total', value: metrics.novaadapt_core_requests_total ?? 0, cls: '' },
          { label: 'Unauthorized', value: metrics.novaadapt_core_unauthorized_total ?? 0, cls: metricColor(metrics.novaadapt_core_unauthorized_total ?? 0, 0) },
          { label: 'Rate Limited', value: metrics.novaadapt_core_rate_limited_total ?? 0, cls: metricColor(metrics.novaadapt_core_rate_limited_total ?? 0, 0) },
          { label: 'Server Errors', value: metrics.novaadapt_core_server_errors_total ?? 0, cls: metricColor(metrics.novaadapt_core_server_errors_total ?? 0, 0) },
        ];

        document.getElementById('summary').innerHTML = summary.map(item => `
          <div class=\"card\">
            <div class=\"label\">${item.label}</div>
            <div class=\"value ${item.cls}\">${item.value}</div>
          </div>
        `).join('');

        jobsTbody.innerHTML = (jobs || []).map(job => {
          const status = String(job.status || '');
          const metadata = job.metadata && typeof job.metadata === 'object' ? job.metadata : {};
          const kind = String(job.kind || metadata.kind || 'run');
          const objective = String(job.objective || metadata.objective || '');
          const result = job.result && typeof job.result === 'object' ? job.result : null;
          const resultSummary = summarizeJobResult(result, kind);
          const repairSummary = summarizeRepair(result?.repair, result?.results);
          const collaborationSummary = summarizeCollaboration(result?.vote_summary, result?.collaboration, result?.strategy || kind);
          const transcriptLines = transcriptPreviewLines(result?.collaboration);
          const canCancel = status === 'running' || status === 'queued';
          const actionCell = canCancel
            ? `<button class="mini warn" data-action="cancel-job" data-id="${escapeHTML(job.id)}">Cancel</button>`
            : '';
          return `
          <tr>
            <td class=\"mono\">${escapeHTML(job.id)}</td>
            <td>
              <div>${escapeHTML(status)}</div>
              <div class=\"detail\">${escapeHTML(kind)}</div>
            </td>
            <td>
              <div>${escapeHTML(objective || '(no objective)')}</div>
              ${resultSummary ? `<div class=\"detail\">${escapeHTML(resultSummary)}</div>` : ''}
              ${job.error ? `<div class=\"detail\">Error: ${escapeHTML(job.error)}</div>` : ''}
              ${repairSummary ? `<div class=\"detail\">Repair: ${escapeHTML(repairSummary)}</div>` : ''}
              ${collaborationSummary ? `<div class=\"detail\">Collab: ${escapeHTML(collaborationSummary)}</div>` : ''}
              ${transcriptLines.length ? `<div class=\"detail\">${transcriptLines.map(line => `• ${escapeHTML(line)}`).join('<br />')}</div>` : ''}
            </td>
            <td>${escapeHTML(job.created_at || '')}</td>
            <td>${escapeHTML(job.finished_at || '')}</td>
            <td>${actionCell}</td>
          </tr>
        `;
        }).join('');

        plansTbody.innerHTML = (plans || []).map(plan => {
          const status = String(plan.status || '');
          const repairSummary = summarizeRepair(plan.repair, plan.execution_results);
          const collaborationSummary = summarizeCollaboration(plan.vote_summary, plan.collaboration, plan.strategy);
          const transcriptLines = transcriptPreviewLines(plan.collaboration);
          let actionCell = '';
          if (status === 'pending') {
            actionCell = `
              <button class="mini" data-action="approve-plan" data-id="${escapeHTML(plan.id)}">Approve Async</button>
              <button class="mini warn" data-action="reject-plan" data-id="${escapeHTML(plan.id)}">Reject</button>
            `;
          } else if (status === 'executed' || status === 'failed' || status === 'approved') {
            actionCell = `<button class="mini" data-action="undo-plan" data-id="${escapeHTML(plan.id)}">Undo Mark</button>`;
            if (status === 'failed') {
              actionCell = `
                <button class="mini" data-action="retry-failed-plan" data-id="${escapeHTML(plan.id)}">Retry Failed</button>
                ${actionCell}
              `;
            }
          }
          return `
          <tr>
            <td class=\"mono\">${escapeHTML(plan.id)}</td>
            <td>${escapeHTML(status)}</td>
            <td>${Number(plan.progress_completed || 0)}/${Number(plan.progress_total || 0)}</td>
            <td>
              <div>${escapeHTML(String(plan.objective || '').slice(0, 120))}</div>
              ${plan.execution_error ? `<div class=\"detail\">Error: ${escapeHTML(plan.execution_error)}</div>` : ''}
              ${repairSummary ? `<div class=\"detail\">Repair: ${escapeHTML(repairSummary)}</div>` : ''}
              ${collaborationSummary ? `<div class=\"detail\">Collab: ${escapeHTML(collaborationSummary)}</div>` : ''}
              ${transcriptLines.length ? `<div class=\"detail\">${transcriptLines.map(line => `• ${escapeHTML(line)}`).join('<br />')}</div>` : ''}
            </td>
            <td>${escapeHTML(plan.created_at || '')}</td>
            <td>${actionCell}</td>
          </tr>
        `;
        }).join('');

        document.getElementById('events').innerHTML = (events || []).map(event => `
          <tr>
            <td class=\"mono\">${escapeHTML(event.id ?? '')}</td>
            <td>${escapeHTML(event.category || '')}</td>
            <td>${escapeHTML(event.action || '')}</td>
            <td>${escapeHTML(event.status || '')}</td>
            <td class=\"mono\">${escapeHTML(event.entity_type && event.entity_id ? `${event.entity_type}:${event.entity_id}` : '')}</td>
            <td>${escapeHTML(event.created_at || '')}</td>
          </tr>
        `).join('');
        renderObservability(observability);
        renderArtifacts(controlArtifacts);
        syncGovernanceInputs(governance);
      } catch (err) {
        document.getElementById('summary').innerHTML = `
          <div class=\"card\">
            <div class=\"label\">Error</div>
            <div class=\"value bad\">${String(err)}</div>
          </div>
        `;
        jobsTbody.innerHTML = '';
        plansTbody.innerHTML = '';
        document.getElementById('events').innerHTML = '';
        observabilityEl.innerHTML = '';
        artifactsEl.innerHTML = '';
      } finally {
        state.refreshInFlight = false;
      }
    }

    document.getElementById('refresh').addEventListener('click', refresh);
    runAsyncButton.addEventListener('click', () => handleOperatorAction('run'));
    createPlanButton.addEventListener('click', () => handleOperatorAction('plan'));
    applyGovernanceButton.addEventListener('click', () => handleGovernanceAction('apply'));
    togglePauseButton.addEventListener('click', () => handleGovernanceAction('togglePause'));
    resetUsageButton.addEventListener('click', () => handleGovernanceAction('resetUsage'));
    cancelAllJobsButton.addEventListener('click', () => handleGovernanceAction('cancelAll'));
    document.getElementById('auto').addEventListener('click', () => {
      state.auto = !state.auto;
      document.getElementById('auto').textContent = `Auto: ${state.auto ? 'On' : 'Off'}`;
      if (state.timer) clearInterval(state.timer);
      if (state.auto) state.timer = setInterval(refresh, 3000);
    });
    liveButton.addEventListener('click', toggleLiveStream);
    jobsTbody.addEventListener('click', handleTableAction);
    plansTbody.addEventListener('click', handleTableAction);

    updateLiveButton();
    refresh();
  </script>
</body>
</html>
"""


def render_canvas_workflows_html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>NovaAdapt Canvas + Workflows Inspector</title>
  <style>
    :root {
      --bg: #0a101a;
      --panel: #101a2a;
      --panel-2: #172235;
      --text: #d8e3f0;
      --muted: #91a0b5;
      --line: #2b3a54;
      --accent: #4bb3fd;
      --ok: #53d18c;
      --warn: #efb949;
      --bad: #f77979;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(900px 450px at 15% -10%, #1b2a44 0%, transparent 42%),
        radial-gradient(700px 400px at 100% -15%, #0f3e59 0%, transparent 38%),
        var(--bg);
      min-height: 100vh;
    }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 18px; }
    h1 { margin: 0 0 6px; font-size: 25px; }
    .sub { margin: 0 0 14px; color: var(--muted); }
    .nav { display: flex; gap: 8px; margin: 0 0 12px; }
    .nav a {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 13px;
    }
    .grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      padding: 12px;
    }
    .card h2 {
      margin: 0 0 10px;
      font-size: 13px;
      letter-spacing: .05em;
      text-transform: uppercase;
      color: var(--muted);
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .row { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; margin-bottom: 8px; }
    .row.single { grid-template-columns: 1fr; }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0c1422;
      color: var(--text);
      padding: 8px;
      font: inherit;
      font-size: 13px;
    }
    textarea {
      min-height: 110px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    button {
      border: 1px solid var(--line);
      background: #162742;
      color: var(--text);
      border-radius: 8px;
      padding: 8px 11px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    .stack { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    .json {
      margin-top: 8px;
      border: 1px solid var(--line);
      background: #09111d;
      border-radius: 8px;
      padding: 8px;
      min-height: 90px;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.4;
    }
    .status { font-size: 12px; margin-top: 8px; color: var(--muted); }
    .status.ok { color: var(--ok); }
    .status.warn { color: var(--warn); }
    .status.bad { color: var(--bad); }
    .checkbox {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text);
      text-transform: none;
      letter-spacing: 0;
      margin: 0;
    }
    .checkbox input { width: auto; }
    .hint {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.4;
    }
    .hint-panel {
      margin-top: 6px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0c1422;
      color: var(--text);
      padding: 8px;
      font-size: 12px;
      line-height: 1.45;
    }
    .posture-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.4;
    }
    .posture-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 3px 10px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: var(--text);
      background: #0c1422;
    }
    .posture-badge.strict {
      border-color: color-mix(in oklab, var(--ok), #000 20%);
      color: var(--ok);
    }
    .posture-badge.balanced {
      border-color: color-mix(in oklab, var(--warn), #000 20%);
      color: var(--warn);
    }
    .posture-badge.lab {
      border-color: color-mix(in oklab, var(--bad), #000 20%);
      color: var(--bad);
    }
    .posture-badge.custom {
      border-color: var(--accent);
      color: var(--accent);
    }
    .risk-banner {
      margin-top: 8px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0c1422;
      font-size: 12px;
      line-height: 1.4;
      color: var(--muted);
    }
    .risk-banner.warn {
      border-color: color-mix(in oklab, var(--warn), #000 15%);
      color: var(--warn);
    }
    .risk-banner.bad {
      border-color: color-mix(in oklab, var(--bad), #000 15%);
      color: var(--bad);
    }
    .risk-banner.hidden {
      display: none;
    }
    .safety-summary {
      margin-top: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0c1422;
      color: var(--text);
      padding: 7px 9px;
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      line-height: 1.35;
      word-break: break-word;
    }
    .safety-summary-row {
      margin-top: 8px;
      display: flex;
      gap: 8px;
      align-items: stretch;
      flex-wrap: wrap;
    }
    .safety-summary-row .safety-summary {
      margin-top: 0;
      flex: 1 1 320px;
    }
    button.compact {
      padding: 6px 10px;
      font-size: 12px;
      align-self: center;
    }
    button.compact.copied {
      border-color: color-mix(in oklab, var(--ok), #000 20%);
      color: var(--ok);
    }
    .posture-legend {
      border: 1px dashed var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      cursor: help;
      user-select: none;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .json.compact {
      min-height: 70px;
      max-height: 190px;
    }
    @media (max-width: 760px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Canvas + Workflows Inspector</h1>
    <p class=\"sub\">Optional operator UI for the new canvas/workflow surfaces. This page requires the dedicated UI flag.</p>
    <div class=\"nav\">
      <a id=\"back-dashboard\" href=\"/dashboard\">Core Dashboard</a>
    </div>
    <div class=\"grid\">
      <section class=\"card\">
        <h2>Canvas</h2>
        <div class=\"row\">
          <div>
            <label for=\"canvas-context\">Context</label>
            <select id=\"canvas-context\">
              <option value=\"api\">api</option>
              <option value=\"cli\">cli</option>
              <option value=\"mcp\">mcp</option>
            </select>
          </div>
          <div>
            <label for=\"canvas-session\">Session ID</label>
            <input id=\"canvas-session\" value=\"default\" />
          </div>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"canvas-title\">Title</label>
            <input id=\"canvas-title\" value=\"Aetherion Snapshot\" />
          </div>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"canvas-sections\">Sections JSON Array</label>
            <textarea id=\"canvas-sections\">[{"heading":"Trade","body":"Market stable","meta":"live"}]</textarea>
          </div>
        </div>
        <div class=\"stack\">
          <button id=\"canvas-status-btn\">Status</button>
          <button id=\"canvas-render-btn\">Render</button>
          <button id=\"canvas-frames-btn\">Frames</button>
        </div>
        <div id=\"canvas-status\" class=\"status\"></div>
        <pre id=\"canvas-json\" class=\"json\"></pre>
      </section>

      <section class=\"card\">
        <h2>Workflows</h2>
        <div class=\"row\">
          <div>
            <label for=\"wf-context\">Context</label>
            <select id=\"wf-context\">
              <option value=\"api\">api</option>
              <option value=\"cli\">cli</option>
              <option value=\"mcp\">mcp</option>
            </select>
          </div>
          <div>
            <label for=\"wf-id\">Workflow ID</label>
            <input id=\"wf-id\" value=\"wf-demo\" />
          </div>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"wf-objective\">Objective</label>
            <input id=\"wf-objective\" value=\"Patrol route in Aetherion\" />
          </div>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"wf-steps\">Steps JSON Array</label>
            <textarea id=\"wf-steps\">[{"name":"scan"},{"name":"report"}]</textarea>
          </div>
        </div>
        <div class=\"stack\">
          <button id=\"wf-status-btn\">Status</button>
          <button id=\"wf-start-btn\">Start</button>
          <button id=\"wf-advance-btn\">Advance</button>
          <button id=\"wf-resume-btn\">Resume</button>
          <button id=\"wf-get-btn\">Get</button>
          <button id=\"wf-list-btn\">List</button>
        </div>
        <div id=\"wf-status\" class=\"status\"></div>
        <pre id=\"wf-json\" class=\"json\"></pre>
      </section>

      <section class=\"card\">
        <h2>Presets + Safety</h2>
        <div class=\"row\">
          <div>
            <label for=\"preset-name\">Preset Name</label>
            <input id=\"preset-name\" placeholder=\"aetherion-monitor\" />
          </div>
          <div>
            <label for=\"preset-select\">Saved Presets</label>
            <select id=\"preset-select\">
              <option value=\"\">(none)</option>
            </select>
          </div>
        </div>
        <div class=\"stack\">
          <button id=\"preset-save-btn\">Save Preset</button>
          <button id=\"preset-load-btn\">Load Preset</button>
          <button id=\"preset-delete-btn\">Delete Preset</button>
        </div>
        <div class=\"stack\">
          <button id=\"preset-export-btn\">Export Bundle</button>
          <button id=\"preset-import-btn\">Import Bundle</button>
          <input id=\"preset-import-file\" type=\"file\" accept=\"application/json,.json\" style=\"display:none\" />
        </div>
        <div class=\"row single\">
          <div>
            <label class=\"checkbox\" for=\"preset-import-preview\">
              <input id=\"preset-import-preview\" type=\"checkbox\" checked />
              Preview dry-run diff before replacing existing preset names
            </label>
          </div>
        </div>
        <div class=\"row\">
          <div>
            <label for=\"safety-profile\">Safety Lock Profile</label>
            <select id=\"safety-profile\">
              <option value=\"strict\">strict</option>
              <option value=\"balanced\">balanced</option>
              <option value=\"lab\">lab</option>
              <option value=\"custom\" disabled>custom (derived)</option>
            </select>
          </div>
          <div>
            <label for=\"safety-profile-apply-btn\">Profile Action</label>
            <button id=\"safety-profile-apply-btn\">Apply Profile</button>
          </div>
        </div>
        <div class=\"hint\">`strict`: confirm + diff preview. `balanced`: confirm only. `lab`: both disabled for controlled local experiments.</div>
        <div class=\"posture-row\">
          <span>Active Safety Posture</span>
          <span id=\"safety-posture-badge\" class=\"posture-badge\">strict</span>
          <span
            id=\"safety-posture-legend\"
            class=\"posture-legend\"
            title=\"strict=production/shared operators; balanced=trusted operator sessions; lab=local sandbox experiments only; custom=manual toggle mix\"
            aria-label=\"Safety posture legend tooltip\"
          >Legend?</span>
        </div>
        <div id=\"safety-risk-banner\" class=\"risk-banner hidden\"></div>
        <div class=\"safety-summary-row\">
          <div id=\"safety-inline-summary\" class=\"safety-summary\"></div>
          <button id=\"safety-summary-copy-btn\" class=\"compact\" title=\"Copy safety summary\">Copy</button>
          <label class=\"checkbox\" for=\"safety-summary-include-ts\">
            <input id=\"safety-summary-include-ts\" type=\"checkbox\" />
            Include UTC timestamp
          </label>
        </div>
        <div id=\"safety-copy-live\" class=\"sr-only\" aria-live=\"polite\" aria-atomic=\"true\"></div>
        <div class=\"hint\">Shortcut: `Ctrl/Cmd+Shift+C` copies the inline safety summary when not typing in inputs.</div>
        <div class=\"hint\">Badge reflects live toggles and can read `strict`, `balanced`, `lab`, or `custom`.</div>
        <div class=\"stack\">
          <button id=\"prefs-reset-btn\">Reset Operator Preferences</button>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"preset-import-diff\">Import Diff Preview</label>
            <pre id=\"preset-import-diff\" class=\"json compact\"></pre>
          </div>
        </div>
        <div class=\"stack\">
          <button id=\"template-aetherion-btn\">Template: Aetherion Monitor</button>
          <button id=\"template-patrol-btn\">Template: Patrol Cycle</button>
          <button id=\"template-reset-btn\">Template: Minimal Safe</button>
        </div>
        <div class=\"row single\">
          <div>
            <label for=\"template-policy-hint\">Template Policy Hint</label>
            <div id=\"template-policy-hint\" class=\"hint-panel\"></div>
          </div>
        </div>
        <div class=\"row single\">
          <div>
            <label class=\"checkbox\" for=\"confirm-mutations\">
              <input id=\"confirm-mutations\" type=\"checkbox\" checked />
              Require confirmation before mutating actions (render/start/advance/resume)
            </label>
            <div class=\"hint\">Keep this enabled in production. Disable only for local controlled testing.</div>
          </div>
        </div>
        <div id=\"preset-status\" class=\"status\"></div>
      </section>
    </div>
  </div>

  <script>
    const token = new URLSearchParams(window.location.search).get('token');
    const PRESET_KEY = 'novaadapt_canvas_workflow_presets_v1';
    const UI_PREFS_KEY = 'novaadapt_canvas_workflow_ui_prefs_v1';
    const DEFAULT_SAFETY_PROFILE = 'strict';
    const CUSTOM_SAFETY_PROFILE = 'custom';
    const SAFETY_PROFILES = {
      strict: { confirmMutations: true, presetImportPreview: true },
      balanced: { confirmMutations: true, presetImportPreview: false },
      lab: { confirmMutations: false, presetImportPreview: false },
    };
    const PRESET_BUNDLE_KIND = 'novaadapt_canvas_workflow_presets_bundle';
    const PRESET_BUNDLE_VERSION = 1;
    const SNAPSHOT_FIELDS = [
      'canvasContext',
      'canvasSession',
      'canvasTitle',
      'canvasSections',
      'workflowContext',
      'workflowId',
      'workflowObjective',
      'workflowSteps',
    ];
    const TEMPLATE_POLICY_HINTS = {
      aetherion: 'Policy hint (Aetherion Monitor): keep confirmation enabled and verify outputs before publishing operational summaries.',
      patrol: 'Policy hint (Patrol Cycle): confirm workflow_id belongs to the active patrol before each advance/resume mutation.',
      reset: 'Policy hint (Minimal Safe): baseline read-first defaults for controlled testing before using mutating actions.',
    };

    function withToken(path){
      if (!token) return path;
      const sep = path.includes('?') ? '&' : '?';
      return `${path}${sep}token=${encodeURIComponent(token)}`;
    }

    function headers(includeJSON=false){
      const out = {};
      if (token) out['Authorization'] = `Bearer ${token}`;
      if (includeJSON) out['Content-Type'] = 'application/json';
      return out;
    }

    function stringify(value){
      try { return JSON.stringify(value, null, 2); }
      catch { return String(value); }
    }

    function parseJSONArea(id, fallback){
      const raw = document.getElementById(id).value.trim();
      if (!raw) return fallback;
      const parsed = JSON.parse(raw);
      return parsed;
    }

    function setStatus(id, text, kind){
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = `status ${kind || ''}`;
    }

    function defaultTemplate(kind){
      if (kind === 'aetherion') {
        return {
          canvasContext: 'api',
          canvasSession: 'aetherion-live',
          canvasTitle: 'Aetherion District Snapshot',
          canvasSections: JSON.stringify([
            { heading: 'Market', body: 'Listings + demand stable', meta: 'economic' },
            { heading: 'Defense', body: 'Sentinel readiness nominal', meta: 'security' },
          ], null, 0),
          workflowContext: 'api',
          workflowId: 'wf-aetherion-monitor',
          workflowObjective: 'Collect district snapshot and publish operator summary',
          workflowSteps: JSON.stringify([
            { name: 'fetch_market' },
            { name: 'fetch_presence' },
            { name: 'summarize' },
          ], null, 0),
        };
      }
      if (kind === 'patrol') {
        return {
          canvasContext: 'api',
          canvasSession: 'patrol-route',
          canvasTitle: 'Patrol Route Board',
          canvasSections: JSON.stringify([
            { heading: 'Route', body: 'East gate -> mid ring -> archive lane', meta: 'pathing' },
            { heading: 'Watchpoints', body: '3 anomalies flagged for follow-up', meta: 'alerts' },
          ], null, 0),
          workflowContext: 'api',
          workflowId: 'wf-patrol-cycle',
          workflowObjective: 'Run patrol cycle and report anomalies',
          workflowSteps: JSON.stringify([
            { name: 'scan_route' },
            { name: 'triage_alerts' },
            { name: 'send_report' },
          ], null, 0),
        };
      }
      return {
        canvasContext: 'api',
        canvasSession: 'default',
        canvasTitle: 'Aetherion Snapshot',
        canvasSections: '[{"heading":"Trade","body":"Market stable","meta":"live"}]',
        workflowContext: 'api',
        workflowId: 'wf-demo',
        workflowObjective: 'Patrol route in Aetherion',
        workflowSteps: '[{"name":"scan"},{"name":"report"}]',
      };
    }

    function readFormSnapshot(){
      return {
        canvasContext: document.getElementById('canvas-context').value,
        canvasSession: document.getElementById('canvas-session').value,
        canvasTitle: document.getElementById('canvas-title').value,
        canvasSections: document.getElementById('canvas-sections').value,
        workflowContext: document.getElementById('wf-context').value,
        workflowId: document.getElementById('wf-id').value,
        workflowObjective: document.getElementById('wf-objective').value,
        workflowSteps: document.getElementById('wf-steps').value,
      };
    }

    function applySnapshot(snapshot){
      if (!snapshot || typeof snapshot !== 'object') return;
      if (typeof snapshot.canvasContext === 'string') document.getElementById('canvas-context').value = snapshot.canvasContext;
      if (typeof snapshot.canvasSession === 'string') document.getElementById('canvas-session').value = snapshot.canvasSession;
      if (typeof snapshot.canvasTitle === 'string') document.getElementById('canvas-title').value = snapshot.canvasTitle;
      if (typeof snapshot.canvasSections === 'string') document.getElementById('canvas-sections').value = snapshot.canvasSections;
      if (typeof snapshot.workflowContext === 'string') document.getElementById('wf-context').value = snapshot.workflowContext;
      if (typeof snapshot.workflowId === 'string') document.getElementById('wf-id').value = snapshot.workflowId;
      if (typeof snapshot.workflowObjective === 'string') document.getElementById('wf-objective').value = snapshot.workflowObjective;
      if (typeof snapshot.workflowSteps === 'string') document.getElementById('wf-steps').value = snapshot.workflowSteps;
    }

    function readPresets(){
      try {
        const raw = localStorage.getItem(PRESET_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
        return parsed;
      } catch (_err) {
        return {};
      }
    }

    function writePresets(presets){
      localStorage.setItem(PRESET_KEY, JSON.stringify(presets || {}));
    }

    function readUIPrefs(){
      try {
        const raw = localStorage.getItem(UI_PREFS_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
        return parsed;
      } catch (_err) {
        return {};
      }
    }

    function writeUIPrefs(nextPrefs){
      const prefs = nextPrefs && typeof nextPrefs === 'object' && !Array.isArray(nextPrefs) ? nextPrefs : {};
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify(prefs));
    }

    function normalizeSafetyProfile(profile){
      const raw = String(profile || '').trim().toLowerCase();
      if (raw === CUSTOM_SAFETY_PROFILE) return CUSTOM_SAFETY_PROFILE;
      return Object.prototype.hasOwnProperty.call(SAFETY_PROFILES, raw) ? raw : DEFAULT_SAFETY_PROFILE;
    }

    function deriveActiveSafetyPosture(){
      const confirmMutations = Boolean(document.getElementById('confirm-mutations').checked);
      const presetImportPreview = Boolean(document.getElementById('preset-import-preview').checked);
      if (confirmMutations && presetImportPreview) return 'strict';
      if (confirmMutations && !presetImportPreview) return 'balanced';
      if (!confirmMutations && !presetImportPreview) return 'lab';
      return 'custom';
    }

    function updateSafetyPostureBadge(){
      const posture = deriveActiveSafetyPosture();
      const badge = document.getElementById('safety-posture-badge');
      if (!badge) return posture;
      badge.textContent = posture;
      badge.className = `posture-badge ${posture}`;
      return posture;
    }

    function updateSafetyRiskBanner(posture){
      const banner = document.getElementById('safety-risk-banner');
      const summary = document.getElementById('safety-inline-summary');
      if (summary) summary.textContent = mutationSafetySummary();
      if (!banner) return;
      const current = posture || deriveActiveSafetyPosture();
      if (current === 'lab') {
        banner.className = 'risk-banner bad';
        banner.textContent = 'Lab posture active: mutating actions can run without confirmation and diff preview. Use only in isolated local testing.';
        return;
      }
      if (current === 'custom') {
        banner.className = 'risk-banner warn';
        banner.textContent = 'Custom posture active: manual safety toggles diverge from profile defaults. Review settings before mutating actions.';
        return;
      }
      banner.className = 'risk-banner hidden';
      banner.textContent = '';
    }

    function profileDefaults(profile){
      const normalized = normalizeSafetyProfile(profile);
      return SAFETY_PROFILES[normalized] || SAFETY_PROFILES[DEFAULT_SAFETY_PROFILE];
    }

    function applyUIPrefsToControls(){
      const prefs = readUIPrefs();
      const profile = normalizeSafetyProfile(prefs.safetyProfile);
      const defaults = profileDefaults(profile);
      const confirmMutations = document.getElementById('confirm-mutations');
      const presetImportPreview = document.getElementById('preset-import-preview');
      const safetyProfile = document.getElementById('safety-profile');
      const summaryTimestamp = document.getElementById('safety-summary-include-ts');
      if (safetyProfile) safetyProfile.value = profile;
      const confirmValue = typeof prefs.confirmMutations === 'boolean' ? prefs.confirmMutations : defaults.confirmMutations;
      const previewValue = typeof prefs.presetImportPreview === 'boolean' ? prefs.presetImportPreview : defaults.presetImportPreview;
      const copySummaryTimestamp = typeof prefs.copySummaryTimestamp === 'boolean' ? prefs.copySummaryTimestamp : false;
      confirmMutations.checked = Boolean(confirmValue);
      presetImportPreview.checked = Boolean(previewValue);
      if (summaryTimestamp) summaryTimestamp.checked = Boolean(copySummaryTimestamp);
      if (profile !== CUSTOM_SAFETY_PROFILE) {
        const profileMatches =
          Boolean(confirmValue) === Boolean(defaults.confirmMutations)
          && Boolean(previewValue) === Boolean(defaults.presetImportPreview);
        if (!profileMatches && safetyProfile) safetyProfile.value = CUSTOM_SAFETY_PROFILE;
      }
      updateSafetyRiskBanner(updateSafetyPostureBadge());
    }

    function persistUIPrefsFromControls(forcedProfile){
      const confirmMutations = document.getElementById('confirm-mutations');
      const presetImportPreview = document.getElementById('preset-import-preview');
      const safetyProfile = document.getElementById('safety-profile');
      const summaryTimestamp = document.getElementById('safety-summary-include-ts');
      const selectedProfile = normalizeSafetyProfile(
        forcedProfile || (safetyProfile ? safetyProfile.value : DEFAULT_SAFETY_PROFILE),
      );
      writeUIPrefs({
        confirmMutations: Boolean(confirmMutations && confirmMutations.checked),
        presetImportPreview: Boolean(presetImportPreview && presetImportPreview.checked),
        safetyProfile: selectedProfile,
        copySummaryTimestamp: Boolean(summaryTimestamp && summaryTimestamp.checked),
      });
      updateSafetyRiskBanner(updateSafetyPostureBadge());
    }

    function applySafetyProfile(profile, includeStatus=true){
      const normalized = normalizeSafetyProfile(profile);
      if (normalized === CUSTOM_SAFETY_PROFILE) {
        setStatus('preset-status', 'Custom posture is derived from manual toggle changes', 'warn');
        return;
      }
      const defaults = profileDefaults(normalized);
      const confirmMutations = document.getElementById('confirm-mutations');
      const presetImportPreview = document.getElementById('preset-import-preview');
      const safetyProfile = document.getElementById('safety-profile');
      confirmMutations.checked = Boolean(defaults.confirmMutations);
      presetImportPreview.checked = Boolean(defaults.presetImportPreview);
      if (safetyProfile) safetyProfile.value = normalized;
      persistUIPrefsFromControls(normalized);
      if (includeStatus) {
        setStatus(
          'preset-status',
          `Applied safety profile: ${normalized} (confirm=${defaults.confirmMutations ? 'on' : 'off'}, preview=${defaults.presetImportPreview ? 'on' : 'off'})`,
          'ok',
        );
      }
    }

    function onSafetyToggleChanged(){
      const safetyProfile = document.getElementById('safety-profile');
      const selectedProfile = normalizeSafetyProfile(safetyProfile ? safetyProfile.value : DEFAULT_SAFETY_PROFILE);
      if (selectedProfile !== CUSTOM_SAFETY_PROFILE) {
        const defaults = profileDefaults(selectedProfile);
        const confirmMutations = Boolean(document.getElementById('confirm-mutations').checked);
        const presetImportPreview = Boolean(document.getElementById('preset-import-preview').checked);
        const profileMatches =
          confirmMutations === Boolean(defaults.confirmMutations)
          && presetImportPreview === Boolean(defaults.presetImportPreview);
        if (!profileMatches && safetyProfile) safetyProfile.value = CUSTOM_SAFETY_PROFILE;
      }
      persistUIPrefsFromControls();
    }

    function mutationSafetySummary(){
      const posture = deriveActiveSafetyPosture();
      const safetyProfile = normalizeSafetyProfile(document.getElementById('safety-profile').value);
      const confirmMutations = Boolean(document.getElementById('confirm-mutations').checked);
      const presetImportPreview = Boolean(document.getElementById('preset-import-preview').checked);
      return `Safety posture=${posture}, profile=${safetyProfile}, confirm=${confirmMutations ? 'on' : 'off'}, import_preview=${presetImportPreview ? 'on' : 'off'}`;
    }

    function buildCopySafetySummary(){
      const base = mutationSafetySummary();
      const includeTimestamp = Boolean(document.getElementById('safety-summary-include-ts').checked);
      if (!includeTimestamp) return base;
      return `${base}, copied_at_utc=${new Date().toISOString()}`;
    }

    function fallbackCopyText(text){
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', 'readonly');
      area.style.position = 'absolute';
      area.style.left = '-9999px';
      document.body.appendChild(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      return Boolean(copied);
    }

    async function copySafetySummary(){
      const text = buildCopySafetySummary();
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          flashCopiedButtonState();
          announceCopyStatus('Safety summary copied to clipboard');
          setStatus('preset-status', 'Safety summary copied', 'ok');
          return;
        }
      } catch (_err) {
        // fallback below
      }
      if (fallbackCopyText(text)) {
        flashCopiedButtonState();
        announceCopyStatus('Safety summary copied to clipboard');
        setStatus('preset-status', 'Safety summary copied', 'ok');
      } else {
        announceCopyStatus('Safety summary copy failed: clipboard unavailable');
        setStatus('preset-status', 'Copy failed: clipboard unavailable', 'warn');
      }
    }

    function announceCopyStatus(message){
      const live = document.getElementById('safety-copy-live');
      if (!live) return;
      live.textContent = '';
      window.setTimeout(() => {
        live.textContent = String(message || '');
      }, 0);
    }

    function shortcutInEditableTarget(event){
      const target = event && event.target;
      if (!target || !(target instanceof Element)) return false;
      if (target.closest('textarea')) return true;
      if (target.closest('select')) return true;
      if (target.closest('input')) return true;
      if (target.closest('[contenteditable="true"]')) return true;
      return false;
    }

    function handleCopyShortcut(event){
      const key = String(event && event.key ? event.key : '').toLowerCase();
      const modifier = Boolean(event && (event.ctrlKey || event.metaKey));
      const withShift = Boolean(event && event.shiftKey);
      const withAlt = Boolean(event && event.altKey);
      if (!modifier || !withShift || withAlt || key !== 'c') return;
      if (shortcutInEditableTarget(event)) return;
      event.preventDefault();
      void copySafetySummary();
    }

    function flashCopiedButtonState(){
      const button = document.getElementById('safety-summary-copy-btn');
      if (!button) return;
      if (!button.dataset.defaultLabel) button.dataset.defaultLabel = button.textContent || 'Copy';
      if (button.dataset.flashTimerId) {
        window.clearTimeout(Number(button.dataset.flashTimerId));
      }
      button.textContent = 'Copied';
      button.classList.add('copied');
      const timerId = window.setTimeout(() => {
        button.textContent = button.dataset.defaultLabel || 'Copy';
        button.classList.remove('copied');
        delete button.dataset.flashTimerId;
      }, 1000);
      button.dataset.flashTimerId = String(timerId);
    }

    function resetOperatorPrefs(){
      applySafetyProfile(DEFAULT_SAFETY_PROFILE, false);
      setStatus('preset-status', 'Operator preferences reset to defaults', 'ok');
    }

    function refreshPresetSelect(selected=''){
      const select = document.getElementById('preset-select');
      const presets = readPresets();
      const names = Object.keys(presets).sort();
      select.innerHTML = '<option value="">(none)</option>';
      for (const name of names) {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
      }
      if (selected && presets[selected]) select.value = selected;
    }

    function normalizeSnapshot(snapshot){
      const fallback = defaultTemplate('reset');
      if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) {
        return fallback;
      }
      const normalized = { ...fallback };
      if (typeof snapshot.canvasContext === 'string') normalized.canvasContext = snapshot.canvasContext;
      if (typeof snapshot.canvasSession === 'string') normalized.canvasSession = snapshot.canvasSession;
      if (typeof snapshot.canvasTitle === 'string') normalized.canvasTitle = snapshot.canvasTitle;
      if (typeof snapshot.canvasSections === 'string') normalized.canvasSections = snapshot.canvasSections;
      if (typeof snapshot.workflowContext === 'string') normalized.workflowContext = snapshot.workflowContext;
      if (typeof snapshot.workflowId === 'string') normalized.workflowId = snapshot.workflowId;
      if (typeof snapshot.workflowObjective === 'string') normalized.workflowObjective = snapshot.workflowObjective;
      if (typeof snapshot.workflowSteps === 'string') normalized.workflowSteps = snapshot.workflowSteps;
      return normalized;
    }

    function validPresetName(name){
      return /^[a-z0-9._-]{1,48}$/.test(name);
    }

    function savePreset(){
      const name = document.getElementById('preset-name').value.trim().toLowerCase();
      if (!name || !validPresetName(name)) {
        setStatus('preset-status', 'Invalid preset name. Use 1-48 chars: a-z 0-9 . _ -', 'bad');
        return;
      }
      const presets = readPresets();
      presets[name] = readFormSnapshot();
      writePresets(presets);
      refreshPresetSelect(name);
      setStatus('preset-status', `Preset saved: ${name}`, 'ok');
    }

    function loadPreset(){
      const name = document.getElementById('preset-select').value;
      if (!name) {
        setStatus('preset-status', 'Pick a preset first', 'warn');
        return;
      }
      const presets = readPresets();
      applySnapshot(presets[name]);
      document.getElementById('preset-name').value = name;
      setStatus('preset-status', `Preset loaded: ${name}`, 'ok');
    }

    function deletePreset(){
      const name = document.getElementById('preset-select').value;
      if (!name) {
        setStatus('preset-status', 'Pick a preset first', 'warn');
        return;
      }
      if (!window.confirm(`Delete preset "${name}"?`)) {
        setStatus('preset-status', 'Delete canceled', 'warn');
        return;
      }
      const presets = readPresets();
      delete presets[name];
      writePresets(presets);
      refreshPresetSelect();
      setStatus('preset-status', `Preset deleted: ${name}`, 'ok');
    }

    function exportPresetBundle(){
      const presets = readPresets();
      const bundle = {
        kind: PRESET_BUNDLE_KIND,
        version: PRESET_BUNDLE_VERSION,
        exported_at: new Date().toISOString(),
        presets,
      };
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '').replaceAll('-', '');
      const fileName = `novaadapt-presets-${stamp}.json`;
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus('preset-status', `Preset bundle exported: ${Object.keys(presets).length} preset(s)`, 'ok');
    }

    function buildPresetDiffSummary(existing, imported){
      const added = [];
      const replaced = [];
      for (const name of Object.keys(imported).sort()) {
        const nextSnapshot = imported[name];
        const previous = existing[name];
        if (!previous || typeof previous !== 'object' || Array.isArray(previous)) {
          added.push(name);
          continue;
        }
        const changedFields = SNAPSHOT_FIELDS.filter((field) => String(previous[field] ?? '') !== String(nextSnapshot[field] ?? ''));
        replaced.push({
          name,
          changed_fields: changedFields,
          changed_field_count: changedFields.length,
        });
      }
      return {
        generated_at: new Date().toISOString(),
        added_presets: added,
        replaced_presets: replaced,
      };
    }

    function setImportDiffPreview(payload){
      const target = document.getElementById('preset-import-diff');
      if (!target) return;
      target.textContent = stringify(payload || {});
    }

    function importPresetBundleFromText(rawText){
      let parsed = null;
      try {
        parsed = JSON.parse(rawText || '{}');
      } catch (_err) {
        setStatus('preset-status', 'Import failed: invalid JSON payload', 'bad');
        return;
      }

      let rawPresets = {};
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        if (parsed.kind === PRESET_BUNDLE_KIND && parsed.presets && typeof parsed.presets === 'object' && !Array.isArray(parsed.presets)) {
          rawPresets = parsed.presets;
        } else if (parsed.presets && typeof parsed.presets === 'object' && !Array.isArray(parsed.presets)) {
          rawPresets = parsed.presets;
        } else {
          rawPresets = parsed;
        }
      }

      const imported = {};
      for (const [nameRaw, snapshot] of Object.entries(rawPresets)) {
        const name = String(nameRaw || '').trim().toLowerCase();
        if (!validPresetName(name)) continue;
        imported[name] = normalizeSnapshot(snapshot);
      }
      const importedNames = Object.keys(imported).sort();
      if (!importedNames.length) {
        setStatus('preset-status', 'Import failed: no valid presets found', 'warn');
        setImportDiffPreview({});
        return;
      }

      const existing = readPresets();
      const replaced = importedNames.filter((name) => Object.prototype.hasOwnProperty.call(existing, name));
      const previewSummary = buildPresetDiffSummary(existing, imported);
      setImportDiffPreview(previewSummary);

      const addedCount = importedNames.length - replaced.length;
      const previewEnabled = document.getElementById('preset-import-preview').checked;
      if (previewEnabled && replaced.length > 0) {
        const proceed = window.confirm(
          `Dry-run preview: ${addedCount} new preset(s), ${replaced.length} replacement(s).\nApply this import?`,
        );
        if (!proceed) {
          setStatus('preset-status', 'Import preview generated; apply canceled', 'warn');
          return;
        }
      } else if (replaced.length > 0) {
        const proceed = window.confirm(
          `Import will replace ${replaced.length} existing preset(s). Continue?`,
        );
        if (!proceed) {
          setStatus('preset-status', 'Import canceled', 'warn');
          return;
        }
      }

      writePresets({ ...existing, ...imported });
      refreshPresetSelect(importedNames[0]);
      document.getElementById('preset-name').value = importedNames[0];
      setStatus(
        'preset-status',
        `Preset bundle imported: ${importedNames.length} preset(s)${replaced.length ? `, replaced ${replaced.length}` : ''}`,
        'ok',
      );
    }

    async function handlePresetImportFile(event){
      const input = event && event.target ? event.target : document.getElementById('preset-import-file');
      const file = input && input.files && input.files[0] ? input.files[0] : null;
      if (!file) return;
      try {
        const raw = await file.text();
        importPresetBundleFromText(raw);
      } catch (_err) {
        setStatus('preset-status', 'Import failed: unable to read file', 'bad');
      } finally {
        input.value = '';
      }
    }

    function setTemplatePolicyHint(kind){
      const target = document.getElementById('template-policy-hint');
      if (!target) return;
      const normalized = typeof kind === 'string' ? kind : 'reset';
      target.textContent = TEMPLATE_POLICY_HINTS[normalized] || TEMPLATE_POLICY_HINTS.reset;
    }

    function applyTemplate(kind){
      const snapshot = defaultTemplate(kind);
      applySnapshot(snapshot);
      setTemplatePolicyHint(kind);
      setStatus('preset-status', `Template loaded: ${kind}`, 'ok');
    }

    function mutationAllowed(actionLabel, payload){
      const required = document.getElementById('confirm-mutations').checked;
      if (!required) return true;
      const preview = stringify(payload).slice(0, 500);
      const summary = mutationSafetySummary();
      return window.confirm(`Confirm ${actionLabel}?\n\n${summary}\n\n${preview}`);
    }

    async function getJSON(path){
      const response = await fetch(withToken(path), {
        credentials: 'same-origin',
        headers: headers(false),
      });
      const text = await response.text();
      let parsed = {};
      try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = { raw: text }; }
      if (!response.ok) throw new Error(parsed.error ? `HTTP ${response.status}: ${parsed.error}` : `HTTP ${response.status}`);
      return parsed;
    }

    async function postJSON(path, body){
      const response = await fetch(path, {
        method: 'POST',
        credentials: 'same-origin',
        headers: headers(true),
        body: JSON.stringify(body || {}),
      });
      const text = await response.text();
      let parsed = {};
      try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = { raw: text }; }
      if (!response.ok) throw new Error(parsed.error ? `HTTP ${response.status}: ${parsed.error}` : `HTTP ${response.status}`);
      return parsed;
    }

    async function runCanvas(action){
      const context = document.getElementById('canvas-context').value;
      const session = document.getElementById('canvas-session').value.trim() || 'default';
      const title = document.getElementById('canvas-title').value.trim();
      try {
        let out = {};
        if (action === 'status'){
          out = await getJSON(`/canvas/status?context=${encodeURIComponent(context)}`);
        } else if (action === 'render'){
          const sections = parseJSONArea('canvas-sections', []);
          const requestPayload = {
            title,
            session_id: session,
            sections,
            context,
          };
          if (!mutationAllowed('canvas render', requestPayload)) {
            setStatus('canvas-status', 'Canvas render canceled by operator', 'warn');
            return;
          }
          out = await postJSON('/canvas/render', {
            ...requestPayload,
          });
        } else if (action === 'frames'){
          out = await getJSON(`/canvas/frames?session_id=${encodeURIComponent(session)}&context=${encodeURIComponent(context)}&limit=20`);
        }
        document.getElementById('canvas-json').textContent = stringify(out);
        setStatus('canvas-status', 'Canvas request ok', 'ok');
      } catch (err) {
        document.getElementById('canvas-json').textContent = String(err);
        setStatus('canvas-status', String(err), 'bad');
      }
    }

    async function runWorkflow(action){
      const context = document.getElementById('wf-context').value;
      const workflowId = document.getElementById('wf-id').value.trim();
      const objective = document.getElementById('wf-objective').value.trim();
      try {
        let out = {};
        if (action === 'status'){
          out = await getJSON(`/workflows/status?context=${encodeURIComponent(context)}`);
        } else if (action === 'start'){
          const steps = parseJSONArea('wf-steps', []);
          const requestPayload = {
            objective,
            workflow_id: workflowId,
            steps,
            context,
          };
          if (!mutationAllowed('workflow start', requestPayload)) {
            setStatus('wf-status', 'Workflow start canceled by operator', 'warn');
            return;
          }
          out = await postJSON('/workflows/start', {
            ...requestPayload,
          });
        } else if (action === 'advance'){
          const requestPayload = {
            workflow_id: workflowId,
            result: { ok: true, source: 'ui' },
            context,
          };
          if (!mutationAllowed('workflow advance', requestPayload)) {
            setStatus('wf-status', 'Workflow advance canceled by operator', 'warn');
            return;
          }
          out = await postJSON('/workflows/advance', {
            ...requestPayload,
          });
        } else if (action === 'resume'){
          const requestPayload = { workflow_id: workflowId, context };
          if (!mutationAllowed('workflow resume', requestPayload)) {
            setStatus('wf-status', 'Workflow resume canceled by operator', 'warn');
            return;
          }
          out = await postJSON('/workflows/resume', { workflow_id: workflowId, context });
        } else if (action === 'get'){
          out = await getJSON(`/workflows/item?workflow_id=${encodeURIComponent(workflowId)}&context=${encodeURIComponent(context)}`);
        } else if (action === 'list'){
          out = await getJSON(`/workflows/list?limit=20&context=${encodeURIComponent(context)}`);
        }
        document.getElementById('wf-json').textContent = stringify(out);
        setStatus('wf-status', 'Workflow request ok', 'ok');
      } catch (err) {
        document.getElementById('wf-json').textContent = String(err);
        setStatus('wf-status', String(err), 'bad');
      }
    }

    document.getElementById('canvas-status-btn').addEventListener('click', () => runCanvas('status'));
    document.getElementById('canvas-render-btn').addEventListener('click', () => runCanvas('render'));
    document.getElementById('canvas-frames-btn').addEventListener('click', () => runCanvas('frames'));
    document.getElementById('wf-status-btn').addEventListener('click', () => runWorkflow('status'));
    document.getElementById('wf-start-btn').addEventListener('click', () => runWorkflow('start'));
    document.getElementById('wf-advance-btn').addEventListener('click', () => runWorkflow('advance'));
    document.getElementById('wf-resume-btn').addEventListener('click', () => runWorkflow('resume'));
    document.getElementById('wf-get-btn').addEventListener('click', () => runWorkflow('get'));
    document.getElementById('wf-list-btn').addEventListener('click', () => runWorkflow('list'));
    document.getElementById('preset-save-btn').addEventListener('click', savePreset);
    document.getElementById('preset-load-btn').addEventListener('click', loadPreset);
    document.getElementById('preset-delete-btn').addEventListener('click', deletePreset);
    document.getElementById('preset-export-btn').addEventListener('click', exportPresetBundle);
    document.getElementById('preset-import-btn').addEventListener('click', () => {
      document.getElementById('preset-import-file').click();
    });
    document.getElementById('preset-import-file').addEventListener('change', handlePresetImportFile);
    document.getElementById('template-aetherion-btn').addEventListener('click', () => applyTemplate('aetherion'));
    document.getElementById('template-patrol-btn').addEventListener('click', () => applyTemplate('patrol'));
    document.getElementById('template-reset-btn').addEventListener('click', () => applyTemplate('reset'));
    document.getElementById('confirm-mutations').addEventListener('change', onSafetyToggleChanged);
    document.getElementById('preset-import-preview').addEventListener('change', onSafetyToggleChanged);
    document.getElementById('safety-profile-apply-btn').addEventListener('click', () => {
      applySafetyProfile(document.getElementById('safety-profile').value, true);
    });
    document.getElementById('safety-summary-copy-btn').addEventListener('click', copySafetySummary);
    document.getElementById('safety-summary-include-ts').addEventListener('change', persistUIPrefsFromControls);
    document.getElementById('prefs-reset-btn').addEventListener('click', resetOperatorPrefs);
    window.addEventListener('keydown', handleCopyShortcut);

    const back = document.getElementById('back-dashboard');
    if (token) back.href = `/dashboard?token=${encodeURIComponent(token)}`;

    applyUIPrefsToControls();
    applyTemplate('reset');
    refreshPresetSelect();
    runCanvas('status');
    runWorkflow('status');
  </script>
</body>
</html>
"""
