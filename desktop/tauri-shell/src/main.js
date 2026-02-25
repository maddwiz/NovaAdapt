import { invoke } from "@tauri-apps/api/core";

const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const hasTauri = typeof window !== "undefined" && !!window.__TAURI_INTERNALS__;

const baseUrlInput = document.querySelector("#baseUrl");
const tokenInput = document.querySelector("#token");
const refreshBtn = document.querySelector("#refreshBtn");
const plansEl = document.querySelector("#plans");
const summaryEl = document.querySelector("#summary");
const planCountEl = document.querySelector("#planCount");

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
}

function loadConfig() {
  baseUrlInput.value = localStorage.getItem("novaadapt.desktop.baseUrl") || DEFAULT_BASE_URL;
  tokenInput.value = localStorage.getItem("novaadapt.desktop.token") || "";
}

async function dashboardData(baseUrl, token) {
  if (hasTauri) {
    return invoke("fetch_dashboard_data", {
      baseUrl,
      token: token || null,
    });
  }

  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${baseUrl.replace(/\/$/, "")}/dashboard/data?plans_limit=100`, { headers });
  if (!res.ok) throw new Error(`Dashboard fetch failed (${res.status})`);
  return res.json();
}

async function approvePlan(baseUrl, token, planId) {
  if (hasTauri) {
    return invoke("approve_plan", {
      baseUrl,
      token: token || null,
      planId,
      execute: true,
    });
  }
  return postJSON(baseUrl, token, `/plans/${encodeURIComponent(planId)}/approve`, { execute: true });
}

async function rejectPlan(baseUrl, token, planId, reason) {
  if (hasTauri) {
    return invoke("reject_plan", {
      baseUrl,
      token: token || null,
      planId,
      reason: reason || null,
    });
  }
  return postJSON(baseUrl, token, `/plans/${encodeURIComponent(planId)}/reject`, { reason });
}

async function postJSON(baseUrl, token, path, payload) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

function render(data) {
  const plans = Array.isArray(data?.plans) ? data.plans : [];
  const pending = plans.filter((item) => String(item.status || "").toLowerCase() === "pending");
  planCountEl.textContent = String(pending.length);

  if (!pending.length) {
    plansEl.innerHTML = "<p>No pending plans.</p>";
  } else {
    plansEl.innerHTML = "";
    for (const plan of pending) {
      const card = document.createElement("article");
      card.className = "plan";
      card.innerHTML = `
        <div class="plan-head">
          <strong>${escapeHTML(plan.objective || "(no objective)")}</strong>
          <span class="plan-id">${escapeHTML(plan.id || "")}</span>
        </div>
        <p class="plan-meta">Strategy: ${escapeHTML(plan.strategy || "single")} • Actions: ${(plan.actions || []).length}</p>
        <div class="row">
          <button class="secondary" data-action="approve">Approve + Execute</button>
          <button class="danger" data-action="reject">Reject</button>
        </div>
      `;

      card.querySelector('[data-action="approve"]').addEventListener("click", async () => {
        const { baseUrl, token } = currentConfig();
        await runAction(async () => approvePlan(baseUrl, token, plan.id));
      });

      card.querySelector('[data-action="reject"]').addEventListener("click", async () => {
        const reason = window.prompt("Reject reason", "Operator rejected");
        if (!reason) return;
        const { baseUrl, token } = currentConfig();
        await runAction(async () => rejectPlan(baseUrl, token, plan.id, reason));
      });

      plansEl.appendChild(card);
    }
  }

  const metrics = data?.metrics || {};
  const out = {
    health: data?.health,
    models_count: data?.models_count,
    queued_jobs: (data?.jobs || []).filter((item) => item.status === "queued").length,
    active_jobs: (data?.jobs || []).filter((item) => item.status === "running").length,
    total_plans: plans.length,
    recent_events: (data?.events || []).slice(0, 5),
    metrics,
  };
  summaryEl.textContent = JSON.stringify(out, null, 2);
}

async function refresh() {
  saveConfig();
  const { baseUrl, token } = currentConfig();
  await runAction(async () => {
    const data = await dashboardData(baseUrl, token);
    render(data);
  });
}

async function runAction(fn) {
  refreshBtn.disabled = true;
  try {
    await fn();
  } catch (err) {
    summaryEl.textContent = String(err?.message || err);
  } finally {
    refreshBtn.disabled = false;
  }
}

function escapeHTML(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

refreshBtn.addEventListener("click", () => refresh());
baseUrlInput.addEventListener("change", saveConfig);
tokenInput.addEventListener("change", saveConfig);

loadConfig();
refresh();
