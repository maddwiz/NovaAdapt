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
    .toolbar { margin: 14px 0; display: flex; gap: 8px; }
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
    </div>
    <div class=\"action-status\" id=\"action-status\"></div>

    <div class=\"tables\">
      <div>
        <div class=\"section-title\">Async Jobs</div>
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Status</th>
              <th>Created</th>
              <th>Finished</th>
              <th>Cancel Req</th>
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
              <th>Objective</th>
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
  </div>

  <script>
    const state = { auto: false, timer: null };
    const authToken = new URLSearchParams(window.location.search).get('token');
    const actionStatus = document.getElementById('action-status');
    const jobsTbody = document.getElementById('jobs');
    const plansTbody = document.getElementById('plans');

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

    function escapeHTML(value){
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
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
          const out = await postJSON(`/plans/${encodeURIComponent(id)}/approve_async`, { execute: true });
          setActionStatus(`Queued approval for plan ${id} (job ${out.job_id || 'n/a'})`, true);
        } else if (action === 'reject-plan') {
          const reason = prompt(`Reject plan ${id}. Optional reason:`, 'Operator rejected');
          await postJSON(`/plans/${encodeURIComponent(id)}/reject`, reason ? { reason } : {});
          setActionStatus(`Rejected plan ${id}`, true);
        } else if (action === 'undo-plan') {
          await postJSON(`/plans/${encodeURIComponent(id)}/undo`, { mark_only: true });
          setActionStatus(`Marked plan ${id} action logs as undone`, true);
        } else if (action === 'retry-failed-plan') {
          const out = await postJSON(`/plans/${encodeURIComponent(id)}/retry_failed_async`, {
            allow_dangerous: true,
            action_retry_attempts: 2,
            action_retry_backoff_seconds: 0.2,
          });
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
      try {
        const data = await fetchJSON('/dashboard/data?jobs_limit=25&plans_limit=25&events_limit=25');
        const health = data.health || {};
        const jobs = data.jobs || [];
        const plans = data.plans || [];
        const events = data.events || [];
        const metrics = data.metrics || {};
        const modelsCount = Number(data.models_count || 0);
        const pendingPlans = plans.filter(item => item.status === 'pending').length;
        const runningJobs = jobs.filter(item => item.status === 'running').length;
        const failedAudits = events.filter(item => item.status === 'error' || item.status === 'failed').length;

        const summary = [
          { label: 'Service', value: health.ok ? 'Healthy' : 'Unhealthy', cls: health.ok ? 'ok' : 'bad' },
          { label: 'Configured Models', value: modelsCount, cls: '' },
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
          const canCancel = status === 'running' || status === 'queued';
          const actionCell = canCancel
            ? `<button class="mini warn" data-action="cancel-job" data-id="${escapeHTML(job.id)}">Cancel</button>`
            : '';
          return `
          <tr>
            <td class=\"mono\">${escapeHTML(job.id)}</td>
            <td>${escapeHTML(status)}</td>
            <td>${escapeHTML(job.created_at || '')}</td>
            <td>${escapeHTML(job.finished_at || '')}</td>
            <td>${job.cancel_requested ? 'yes' : 'no'}</td>
            <td>${actionCell}</td>
          </tr>
        `;
        }).join('');

        plansTbody.innerHTML = (plans || []).map(plan => {
          const status = String(plan.status || '');
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
            <td>${escapeHTML(String(plan.objective || '').slice(0, 80))}</td>
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
      }
    }

    document.getElementById('refresh').addEventListener('click', refresh);
    document.getElementById('auto').addEventListener('click', () => {
      state.auto = !state.auto;
      document.getElementById('auto').textContent = `Auto: ${state.auto ? 'On' : 'Off'}`;
      if (state.timer) clearInterval(state.timer);
      if (state.auto) state.timer = setInterval(refresh, 3000);
    });
    jobsTbody.addEventListener('click', handleTableAction);
    plansTbody.addEventListener('click', handleTableAction);

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
    .posture-legend {
      border: 1px dashed var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      cursor: help;
      user-select: none;
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
        <div id=\"safety-inline-summary\" class=\"safety-summary\"></div>
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
      if (safetyProfile) safetyProfile.value = profile;
      const confirmValue = typeof prefs.confirmMutations === 'boolean' ? prefs.confirmMutations : defaults.confirmMutations;
      const previewValue = typeof prefs.presetImportPreview === 'boolean' ? prefs.presetImportPreview : defaults.presetImportPreview;
      confirmMutations.checked = Boolean(confirmValue);
      presetImportPreview.checked = Boolean(previewValue);
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
      const selectedProfile = normalizeSafetyProfile(
        forcedProfile || (safetyProfile ? safetyProfile.value : DEFAULT_SAFETY_PROFILE),
      );
      writeUIPrefs({
        confirmMutations: Boolean(confirmMutations && confirmMutations.checked),
        presetImportPreview: Boolean(presetImportPreview && presetImportPreview.checked),
        safetyProfile: selectedProfile,
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
    document.getElementById('prefs-reset-btn').addEventListener('click', resetOperatorPrefs);

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
