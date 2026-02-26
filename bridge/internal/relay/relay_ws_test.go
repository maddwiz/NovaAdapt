package relay

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestWebSocketUnauthorized(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "bridge"})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws"
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err == nil {
		t.Fatalf("expected websocket auth error")
	}
	if resp == nil || resp.StatusCode != http.StatusUnauthorized {
		if resp == nil {
			t.Fatalf("expected unauthorized response status")
		}
		t.Fatalf("expected 401 got %d", resp.StatusCode)
	}
}

func TestWebSocketUnauthorizedWithMissingDeviceID(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/events/stream" {
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: timeout\ndata: {\"request_id\":\"rid\"}\n\n"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:      core.URL,
			BridgeToken:      "bridge",
			CoreToken:        "coresecret",
			AllowedDeviceIDs: []string{"iphone-1"},
			Timeout:          5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws"
	headers := http.Header{}
	headers.Set("Authorization", "Bearer bridge")
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		t.Fatalf("expected websocket auth error")
	}
	if resp == nil || resp.StatusCode != http.StatusUnauthorized {
		if resp == nil {
			t.Fatalf("expected unauthorized response status")
		}
		t.Fatalf("expected 401 got %d", resp.StatusCode)
	}
}

func TestWebSocketAllowsQueryTokenAndDeviceID(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer coresecret" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized core"}`))
			return
		}
		if r.URL.Path == "/events/stream" {
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: timeout\ndata: {\"request_id\":\"rid\"}\n\n"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:      core.URL,
			BridgeToken:      "bridge",
			CoreToken:        "coresecret",
			AllowedDeviceIDs: []string{"iphone-1"},
			Timeout:          5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?token=bridge&device_id=iphone-1&since_id=0"
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial websocket with query token/device id: %v", err)
	}
	defer conn.Close()

	hello := mustReadWSMessageByType(t, conn, "hello", 2*time.Second)
	if hello["type"] != "hello" {
		t.Fatalf("expected hello, got %#v", hello)
	}
}

func TestWebSocketCommandAndEventStreaming(t *testing.T) {
	eventsRequests := 0
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer coresecret" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized core"}`))
			return
		}
		switch r.URL.Path {
		case "/events/stream":
			eventsRequests++
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			sinceID := r.URL.Query().Get("since_id")
			if sinceID == "0" {
				_, _ = w.Write([]byte("event: audit\ndata: {\"id\":1,\"category\":\"plans\",\"action\":\"approve_async\",\"entity_type\":\"plan\",\"entity_id\":\"plan1\"}\n\n"))
				return
			}
			_, _ = w.Write([]byte("event: timeout\ndata: {\"request_id\":\"rid\"}\n\n"))
		case "/plans/plan1/approve_async":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"execute":true`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing execute true"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-1")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"plan-job-1","status":"queued","kind":"plan_approval"}`))
		case "/plans/plan1/retry_failed_async":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-2")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"plan-job-retry-1","status":"queued","kind":"plan_retry_failed"}`))
		case "/browser/navigate":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"url":"https://example.com"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing url"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"navigated","data":{"url":"https://example.com"}}`))
		case "/browser/status":
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-status")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"ok":true,"browser":"chromium","headless":true}`))
		case "/browser/pages":
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-pages")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"count":1,"current_page_id":"page-1","pages":[{"page_id":"page-1","url":"https://example.com","current":true}]}`))
		case "/browser/click":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"selector":"button.submit"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing selector"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-click")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"clicked","data":{"selector":"button.submit"}}`))
		case "/browser/fill":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"selector":"input[name=email]"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing selector"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-fill")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"filled","data":{"selector":"input[name=email]"}}`))
		case "/browser/extract_text":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"selector":"h1"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing selector"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-extract")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"extracted","data":{"text":"Example Domain"}}`))
		case "/browser/screenshot":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"path":"ws-browser.png"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing path"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-screenshot")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"captured","data":{"path":"ws-browser.png"}}`))
		case "/browser/wait_for_selector":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"selector":"#ready"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing selector"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-wait")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"selector ready","data":{"selector":"#ready"}}`))
		case "/browser/evaluate_js":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"script":"document.title"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing script"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-eval")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"evaluated","data":{"result":"Example Domain"}}`))
		case "/browser/action":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"type":"navigate"`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing action type"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-action")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"action routed","data":{"type":"navigate"}}`))
		case "/browser/close":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-browser-close")
			w.Header().Set("Idempotency-Key", r.Header.Get("Idempotency-Key"))
			w.Header().Set("X-Idempotency-Replayed", "false")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok","output":"closed"}`))
		case "/terminal/sessions":
			if r.Method == http.MethodGet {
				w.Header().Set("X-Request-ID", "core-rid-term-list")
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`[{"id":"term1","open":true}]`))
				return
			}
			if r.Method == http.MethodPost {
				w.Header().Set("X-Request-ID", "core-rid-term-start")
				w.WriteHeader(http.StatusCreated)
				_, _ = w.Write([]byte(`{"id":"term1","open":true,"last_seq":0}`))
				return
			}
			w.WriteHeader(http.StatusMethodNotAllowed)
			_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
		case "/terminal/sessions/term1/output":
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-term-output")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":"term1","open":true,"next_seq":1,"chunks":[{"seq":1,"data":"$ ","stream":"stdout"}]}`))
		case "/terminal/sessions/term1/input":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			raw, _ := io.ReadAll(r.Body)
			if !strings.Contains(string(raw), `"input":"pwd`) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"error":"missing input"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-term-input")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":"term1","accepted":true}`))
		case "/terminal/sessions/term1/close":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				_, _ = w.Write([]byte(`{"error":"method not allowed"}`))
				return
			}
			w.Header().Set("X-Request-ID", "core-rid-term-close")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":"term1","closed":true}`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL: core.URL,
			BridgeToken: "bridge",
			CoreToken:   "coresecret",
			Timeout:     5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?since_id=0&poll_timeout=1&poll_interval=0.05"
	headers := http.Header{}
	headers.Set("Authorization", "Bearer bridge")
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err != nil {
		t.Fatalf("dial websocket: %v", err)
	}
	defer conn.Close()

	hello := mustReadWSMessageByType(t, conn, "hello", 2*time.Second)
	if hello["request_id"] == "" {
		t.Fatalf("expected hello request_id")
	}

	eventMsg := mustReadWSMessageByType(t, conn, "event", 2*time.Second)
	if eventMsg["event"] != "audit" {
		t.Fatalf("expected audit event, got %#v", eventMsg)
	}
	data, ok := eventMsg["data"].(map[string]any)
	if !ok || data["entity_id"] != "plan1" {
		t.Fatalf("unexpected audit payload: %#v", eventMsg["data"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":   "command",
			"id":     "cmd-approve",
			"method": "POST",
			"path":   "/plans/plan1/approve_async",
			"body": map[string]any{
				"execute": true,
			},
			"idempotency_key": "idem-ws-1",
		},
	); err != nil {
		t.Fatalf("write command: %v", err)
	}

	result := mustReadWSMessageByType(t, conn, "command_result", 2*time.Second)
	if result["id"] != "cmd-approve" {
		t.Fatalf("expected command_result id, got %#v", result)
	}
	if int(result["status"].(float64)) != http.StatusAccepted {
		t.Fatalf("expected status 202, got %#v", result["status"])
	}
	payload, ok := result["payload"].(map[string]any)
	if !ok || payload["job_id"] != "plan-job-1" {
		t.Fatalf("unexpected command payload: %#v", result["payload"])
	}
	if result["idempotency_key"] != "idem-ws-1" {
		t.Fatalf("expected idempotency key in command result, got %#v", result["idempotency_key"])
	}
	if result["core_request_id"] != "core-rid-1" {
		t.Fatalf("expected core request id in command result, got %#v", result["core_request_id"])
	}
	if replayed, ok := result["replayed"].(bool); !ok || replayed {
		t.Fatalf("expected replayed=false, got %#v", result["replayed"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":   "command",
			"id":     "cmd-retry",
			"method": "POST",
			"path":   "/plans/plan1/retry_failed_async",
			"body": map[string]any{
				"allow_dangerous": true,
			},
			"idempotency_key": "idem-ws-retry-1",
		},
	); err != nil {
		t.Fatalf("write retry command: %v", err)
	}

	retryResult := mustReadWSMessageByType(t, conn, "command_result", 2*time.Second)
	if retryResult["id"] != "cmd-retry" {
		t.Fatalf("expected retry command_result id, got %#v", retryResult)
	}
	if int(retryResult["status"].(float64)) != http.StatusAccepted {
		t.Fatalf("expected retry status 202, got %#v", retryResult["status"])
	}
	retryPayload, ok := retryResult["payload"].(map[string]any)
	if !ok || retryPayload["kind"] != "plan_retry_failed" {
		t.Fatalf("unexpected retry command payload: %#v", retryResult["payload"])
	}
	if retryResult["idempotency_key"] != "idem-ws-retry-1" {
		t.Fatalf("expected retry idempotency key in command result, got %#v", retryResult["idempotency_key"])
	}
	if retryResult["core_request_id"] != "core-rid-2" {
		t.Fatalf("expected retry core request id in command result, got %#v", retryResult["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":   "command",
			"id":     "cmd-browser-nav",
			"method": "POST",
			"path":   "/browser/navigate",
			"body": map[string]any{
				"url": "https://example.com",
			},
			"idempotency_key": "idem-ws-browser-1",
		},
	); err != nil {
		t.Fatalf("write browser command: %v", err)
	}

	browserResult := mustReadWSMessageByType(t, conn, "command_result", 2*time.Second)
	if browserResult["id"] != "cmd-browser-nav" {
		t.Fatalf("expected browser command_result id, got %#v", browserResult)
	}
	if int(browserResult["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser status 200, got %#v", browserResult["status"])
	}
	browserPayload, ok := browserResult["payload"].(map[string]any)
	if !ok || browserPayload["status"] != "ok" {
		t.Fatalf("unexpected browser command payload: %#v", browserResult["payload"])
	}
	if browserResult["idempotency_key"] != "idem-ws-browser-1" {
		t.Fatalf("expected browser idempotency key in command result, got %#v", browserResult["idempotency_key"])
	}
	if browserResult["core_request_id"] != "core-rid-browser" {
		t.Fatalf("expected browser core request id in command result, got %#v", browserResult["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_status",
			"id":   "browser-status-1",
		},
	); err != nil {
		t.Fatalf("write browser_status: %v", err)
	}
	browserStatus := mustReadWSMessageByType(t, conn, "browser_status", 2*time.Second)
	if browserStatus["id"] != "browser-status-1" {
		t.Fatalf("expected browser status id, got %#v", browserStatus)
	}
	if int(browserStatus["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser status 200, got %#v", browserStatus["status"])
	}
	if browserStatus["core_request_id"] != "core-rid-browser-status" {
		t.Fatalf("expected browser status core request id, got %#v", browserStatus["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_pages",
			"id":   "browser-pages-1",
		},
	); err != nil {
		t.Fatalf("write browser_pages: %v", err)
	}
	browserPages := mustReadWSMessageByType(t, conn, "browser_pages", 2*time.Second)
	if browserPages["id"] != "browser-pages-1" {
		t.Fatalf("expected browser pages id, got %#v", browserPages)
	}
	if int(browserPages["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser pages status 200, got %#v", browserPages["status"])
	}
	if browserPages["core_request_id"] != "core-rid-browser-pages" {
		t.Fatalf("expected browser pages core request id, got %#v", browserPages["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_action",
			"id":   "browser-action-1",
			"body": map[string]any{
				"type":   "navigate",
				"target": "https://example.com",
			},
			"idempotency_key": "idem-ws-browser-action-1",
		},
	); err != nil {
		t.Fatalf("write browser_action: %v", err)
	}
	browserAction := mustReadWSMessageByType(t, conn, "browser_action_result", 2*time.Second)
	if browserAction["id"] != "browser-action-1" {
		t.Fatalf("expected browser action id, got %#v", browserAction)
	}
	if int(browserAction["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser action status 200, got %#v", browserAction["status"])
	}
	if browserAction["core_request_id"] != "core-rid-browser-action" {
		t.Fatalf("expected browser action core request id, got %#v", browserAction["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_navigate",
			"id":   "browser-navigate-1",
			"body": map[string]any{
				"url": "https://example.com",
			},
			"idempotency_key": "idem-ws-browser-nav-typed-1",
		},
	); err != nil {
		t.Fatalf("write browser_navigate: %v", err)
	}
	browserNavigate := mustReadWSMessageByType(t, conn, "browser_navigate_result", 2*time.Second)
	if browserNavigate["id"] != "browser-navigate-1" {
		t.Fatalf("expected browser navigate id, got %#v", browserNavigate)
	}
	if int(browserNavigate["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser navigate status 200, got %#v", browserNavigate["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_click",
			"id":   "browser-click-1",
			"body": map[string]any{
				"selector": "button.submit",
			},
			"idempotency_key": "idem-ws-browser-click-1",
		},
	); err != nil {
		t.Fatalf("write browser_click: %v", err)
	}
	browserClick := mustReadWSMessageByType(t, conn, "browser_click_result", 2*time.Second)
	if browserClick["id"] != "browser-click-1" {
		t.Fatalf("expected browser click id, got %#v", browserClick)
	}
	if int(browserClick["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser click status 200, got %#v", browserClick["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_fill",
			"id":   "browser-fill-1",
			"body": map[string]any{
				"selector": "input[name=email]",
				"value":    "user@example.com",
			},
			"idempotency_key": "idem-ws-browser-fill-1",
		},
	); err != nil {
		t.Fatalf("write browser_fill: %v", err)
	}
	browserFill := mustReadWSMessageByType(t, conn, "browser_fill_result", 2*time.Second)
	if browserFill["id"] != "browser-fill-1" {
		t.Fatalf("expected browser fill id, got %#v", browserFill)
	}
	if int(browserFill["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser fill status 200, got %#v", browserFill["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_extract_text",
			"id":   "browser-extract-1",
			"body": map[string]any{
				"selector": "h1",
			},
			"idempotency_key": "idem-ws-browser-extract-1",
		},
	); err != nil {
		t.Fatalf("write browser_extract_text: %v", err)
	}
	browserExtract := mustReadWSMessageByType(t, conn, "browser_extract_text_result", 2*time.Second)
	if browserExtract["id"] != "browser-extract-1" {
		t.Fatalf("expected browser extract id, got %#v", browserExtract)
	}
	if int(browserExtract["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser extract status 200, got %#v", browserExtract["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_screenshot",
			"id":   "browser-screenshot-1",
			"body": map[string]any{
				"path": "ws-browser.png",
			},
			"idempotency_key": "idem-ws-browser-shot-1",
		},
	); err != nil {
		t.Fatalf("write browser_screenshot: %v", err)
	}
	browserScreenshot := mustReadWSMessageByType(t, conn, "browser_screenshot_result", 2*time.Second)
	if browserScreenshot["id"] != "browser-screenshot-1" {
		t.Fatalf("expected browser screenshot id, got %#v", browserScreenshot)
	}
	if int(browserScreenshot["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser screenshot status 200, got %#v", browserScreenshot["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_wait_for_selector",
			"id":   "browser-wait-1",
			"body": map[string]any{
				"selector": "#ready",
			},
			"idempotency_key": "idem-ws-browser-wait-1",
		},
	); err != nil {
		t.Fatalf("write browser_wait_for_selector: %v", err)
	}
	browserWait := mustReadWSMessageByType(t, conn, "browser_wait_for_selector_result", 2*time.Second)
	if browserWait["id"] != "browser-wait-1" {
		t.Fatalf("expected browser wait id, got %#v", browserWait)
	}
	if int(browserWait["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser wait status 200, got %#v", browserWait["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "browser_evaluate_js",
			"id":   "browser-eval-1",
			"body": map[string]any{
				"script": "document.title",
			},
			"idempotency_key": "idem-ws-browser-eval-1",
		},
	); err != nil {
		t.Fatalf("write browser_evaluate_js: %v", err)
	}
	browserEval := mustReadWSMessageByType(t, conn, "browser_evaluate_js_result", 2*time.Second)
	if browserEval["id"] != "browser-eval-1" {
		t.Fatalf("expected browser eval id, got %#v", browserEval)
	}
	if int(browserEval["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser eval status 200, got %#v", browserEval["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":            "browser_close",
			"id":              "browser-close-1",
			"idempotency_key": "idem-ws-browser-close-1",
		},
	); err != nil {
		t.Fatalf("write browser_close: %v", err)
	}
	browserClosed := mustReadWSMessageByType(t, conn, "browser_closed", 2*time.Second)
	if browserClosed["id"] != "browser-close-1" {
		t.Fatalf("expected browser closed id, got %#v", browserClosed)
	}
	if int(browserClosed["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected browser close status 200, got %#v", browserClosed["status"])
	}
	if browserClosed["core_request_id"] != "core-rid-browser-close" {
		t.Fatalf("expected browser close core request id, got %#v", browserClosed["core_request_id"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "terminal_list",
			"id":   "term-list-1",
		},
	); err != nil {
		t.Fatalf("write terminal_list: %v", err)
	}
	terminalList := mustReadWSMessageByType(t, conn, "terminal_sessions", 2*time.Second)
	if terminalList["id"] != "term-list-1" {
		t.Fatalf("expected terminal list id, got %#v", terminalList)
	}
	if int(terminalList["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected terminal list status 200, got %#v", terminalList["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type": "terminal_start",
			"id":   "term-start-1",
			"body": map[string]any{
				"command": "bash",
			},
		},
	); err != nil {
		t.Fatalf("write terminal_start: %v", err)
	}
	terminalStarted := mustReadWSMessageByType(t, conn, "terminal_started", 2*time.Second)
	if terminalStarted["id"] != "term-start-1" {
		t.Fatalf("expected terminal start id, got %#v", terminalStarted)
	}
	if int(terminalStarted["status"].(float64)) != http.StatusCreated {
		t.Fatalf("expected terminal start status 201, got %#v", terminalStarted["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":       "terminal_poll",
			"id":         "term-poll-1",
			"session_id": "term1",
			"since_seq":  0,
			"limit":      100,
		},
	); err != nil {
		t.Fatalf("write terminal_poll: %v", err)
	}
	terminalOutput := mustReadWSMessageByType(t, conn, "terminal_output", 2*time.Second)
	if terminalOutput["id"] != "term-poll-1" {
		t.Fatalf("expected terminal output id, got %#v", terminalOutput)
	}
	if int(terminalOutput["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected terminal output status 200, got %#v", terminalOutput["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":       "terminal_input",
			"id":         "term-input-1",
			"session_id": "term1",
			"input":      "pwd\n",
		},
	); err != nil {
		t.Fatalf("write terminal_input: %v", err)
	}
	terminalInput := mustReadWSMessageByType(t, conn, "terminal_input_result", 2*time.Second)
	if terminalInput["id"] != "term-input-1" {
		t.Fatalf("expected terminal input id, got %#v", terminalInput)
	}
	if int(terminalInput["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected terminal input status 200, got %#v", terminalInput["status"])
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":       "terminal_close",
			"id":         "term-close-1",
			"session_id": "term1",
		},
	); err != nil {
		t.Fatalf("write terminal_close: %v", err)
	}
	terminalClosed := mustReadWSMessageByType(t, conn, "terminal_closed", 2*time.Second)
	if terminalClosed["id"] != "term-close-1" {
		t.Fatalf("expected terminal close id, got %#v", terminalClosed)
	}
	if int(terminalClosed["status"].(float64)) != http.StatusOK {
		t.Fatalf("expected terminal close status 200, got %#v", terminalClosed["status"])
	}

	if err := conn.WriteJSON(map[string]any{"type": "set_since_id", "id": "cursor-1", "since_id": 1}); err != nil {
		t.Fatalf("write set_since_id: %v", err)
	}
	ack := mustReadWSMessageByType(t, conn, "ack", 2*time.Second)
	if int64(ack["since_id"].(float64)) != 1 {
		t.Fatalf("expected since_id ack 1, got %#v", ack["since_id"])
	}

	if err := conn.WriteJSON(map[string]any{"type": "ping", "id": "ping-1"}); err != nil {
		t.Fatalf("write ping: %v", err)
	}
	pong := mustReadWSMessageByType(t, conn, "pong", 2*time.Second)
	if pong["id"] != "ping-1" {
		t.Fatalf("expected pong id ping-1, got %#v", pong)
	}

	if eventsRequests < 1 {
		t.Fatalf("expected at least one events stream poll")
	}
}

func TestWebSocketConnectionLimit(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/events/stream" {
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: timeout\ndata: {\"request_id\":\"rid\"}\n\n"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:      core.URL,
			BridgeToken:      "bridge",
			CoreToken:        "coresecret",
			MaxWSConnections: 1,
			Timeout:          5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?since_id=0"
	headers := http.Header{}
	headers.Set("Authorization", "Bearer bridge")

	conn1, _, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err != nil {
		t.Fatalf("dial first websocket: %v", err)
	}
	defer conn1.Close()
	_ = mustReadWSMessageByType(t, conn1, "hello", 2*time.Second)

	_, resp, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		t.Fatalf("expected websocket limit error")
	}
	if resp == nil || resp.StatusCode != http.StatusTooManyRequests {
		if resp == nil {
			t.Fatalf("expected too many requests response status")
		}
		t.Fatalf("expected 429 got %d", resp.StatusCode)
	}
}

func mustReadWSMessageByType(
	t *testing.T,
	conn *websocket.Conn,
	typ string,
	timeout time.Duration,
) map[string]any {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if err := conn.SetReadDeadline(time.Now().Add(500 * time.Millisecond)); err != nil {
			t.Fatalf("set read deadline: %v", err)
		}
		var msg map[string]any
		if err := conn.ReadJSON(&msg); err != nil {
			if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
				t.Fatalf("websocket closed before receiving %s: %v", typ, err)
			}
			// Retry while deadline has not elapsed for intermittent read timeouts.
			continue
		}
		if msg["type"] == typ {
			return msg
		}
	}
	t.Fatalf("timed out waiting for websocket message type=%s", typ)
	return nil
}
