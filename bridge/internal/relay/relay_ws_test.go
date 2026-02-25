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
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"plan-job-1","status":"queued","kind":"plan_approval"}`))
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
