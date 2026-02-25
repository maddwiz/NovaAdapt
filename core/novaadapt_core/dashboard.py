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
