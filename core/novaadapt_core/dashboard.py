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
    <div class=\"sub\">Live operational view for health, metrics, and async jobs.</div>

    <div class=\"grid\" id=\"summary\"></div>

    <div class=\"toolbar\">
      <button id=\"refresh\">Refresh</button>
      <button id=\"auto\">Auto: Off</button>
    </div>

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
            </tr>
          </thead>
          <tbody id=\"plans\"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const state = { auto: false, timer: null };
    const authToken = new URLSearchParams(window.location.search).get('token');

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

    async function fetchJSON(path){
      const r = await fetch(withToken(path), { credentials: 'same-origin' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    }

    async function refresh(){
      try {
        const data = await fetchJSON('/dashboard/data?jobs_limit=25&plans_limit=25');
        const health = data.health || {};
        const jobs = data.jobs || [];
        const plans = data.plans || [];
        const metrics = data.metrics || {};
        const modelsCount = Number(data.models_count || 0);
        const pendingPlans = plans.filter(item => item.status === 'pending').length;
        const runningJobs = jobs.filter(item => item.status === 'running').length;

        const summary = [
          { label: 'Service', value: health.ok ? 'Healthy' : 'Unhealthy', cls: health.ok ? 'ok' : 'bad' },
          { label: 'Configured Models', value: modelsCount, cls: '' },
          { label: 'Running Jobs', value: runningJobs, cls: runningJobs > 0 ? 'warn' : 'ok' },
          { label: 'Pending Plans', value: pendingPlans, cls: pendingPlans > 0 ? 'warn' : 'ok' },
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

        document.getElementById('jobs').innerHTML = (jobs || []).map(job => `
          <tr>
            <td class=\"mono\">${job.id}</td>
            <td>${job.status}</td>
            <td>${job.created_at || ''}</td>
            <td>${job.finished_at || ''}</td>
            <td>${job.cancel_requested ? 'yes' : 'no'}</td>
          </tr>
        `).join('');

        document.getElementById('plans').innerHTML = (plans || []).map(plan => `
          <tr>
            <td class=\"mono\">${plan.id}</td>
            <td>${plan.status}</td>
            <td>${Number(plan.progress_completed || 0)}/${Number(plan.progress_total || 0)}</td>
            <td>${String(plan.objective || '').slice(0, 80)}</td>
            <td>${plan.created_at || ''}</td>
          </tr>
        `).join('');
      } catch (err) {
        document.getElementById('summary').innerHTML = `
          <div class=\"card\">
            <div class=\"label\">Error</div>
            <div class=\"value bad\">${String(err)}</div>
          </div>
        `;
        document.getElementById('jobs').innerHTML = '';
        document.getElementById('plans').innerHTML = '';
      }
    }

    document.getElementById('refresh').addEventListener('click', refresh);
    document.getElementById('auto').addEventListener('click', () => {
      state.auto = !state.auto;
      document.getElementById('auto').textContent = `Auto: ${state.auto ? 'On' : 'Off'}`;
      if (state.timer) clearInterval(state.timer);
      if (state.auto) state.timer = setInterval(refresh, 3000);
    });

    refresh();
  </script>
</body>
</html>
"""
