#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use reqwest::Method;
use serde_json::{json, Value};

#[tauri::command]
async fn fetch_dashboard_data(base_url: String, token: Option<String>) -> Result<Value, String> {
    request_json(Method::GET, &base_url, "/dashboard/data?plans_limit=100", token, None).await
}

#[tauri::command]
async fn approve_plan(
    base_url: String,
    token: Option<String>,
    plan_id: String,
    execute: bool,
) -> Result<Value, String> {
    let path = format!("/plans/{}/approve", plan_id);
    request_json(Method::POST, &base_url, &path, token, Some(json!({ "execute": execute }))).await
}

#[tauri::command]
async fn reject_plan(
    base_url: String,
    token: Option<String>,
    plan_id: String,
    reason: Option<String>,
) -> Result<Value, String> {
    let path = format!("/plans/{}/reject", plan_id);
    request_json(
        Method::POST,
        &base_url,
        &path,
        token,
        Some(json!({ "reason": reason.unwrap_or_else(|| "Operator rejected".to_string()) })),
    )
    .await
}

async fn request_json(
    method: Method,
    base_url: &str,
    path: &str,
    token: Option<String>,
    payload: Option<Value>,
) -> Result<Value, String> {
    let base = base_url.trim().trim_end_matches('/');
    if base.is_empty() {
        return Err("Base URL is required".to_string());
    }

    let url = format!("{}{}", base, path);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| format!("HTTP client init failed: {}", e))?;

    let mut req = client.request(method, &url);
    if let Some(tok) = token {
        let trimmed = tok.trim().to_string();
        if !trimmed.is_empty() {
            req = req.bearer_auth(trimmed);
        }
    }
    if let Some(body) = payload {
        req = req.json(&body);
    }

    let response = req.send().await.map_err(|e| format!("Request failed: {}", e))?;
    let status = response.status();
    let body_text = response
        .text()
        .await
        .map_err(|e| format!("Read response failed: {}", e))?;

    if !status.is_success() {
        return Err(format!("Core API {}: {}", status.as_u16(), body_text));
    }

    serde_json::from_str(&body_text).map_err(|e| format!("Invalid JSON from core: {}", e))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            fetch_dashboard_data,
            approve_plan,
            reject_plan
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
