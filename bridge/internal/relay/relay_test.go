package relay

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHealthNoAuth(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "secret"})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d", rr.Code)
	}
	if rr.Header().Get("X-Request-ID") == "" {
		t.Fatalf("expected request id header")
	}
}

func TestHealthDeepChecksCore(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			_, _ = w.Write([]byte(`{"ok":true}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer core.Close()

	h, err := NewHandler(Config{CoreBaseURL: core.URL, BridgeToken: "secret", Timeout: 5 * time.Second})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health?deep=1", nil)
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rr.Code, rr.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	corePayload, ok := payload["core"].(map[string]any)
	if !ok {
		t.Fatalf("expected core payload")
	}
	if reachable, ok := corePayload["reachable"].(bool); !ok || !reachable {
		t.Fatalf("expected core reachable true: %#v", corePayload)
	}
}

func TestUnauthorized(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "secret"})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/models", nil)
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 got %d", rr.Code)
	}
}

func TestForwardArrayWithAuthAndRequestID(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer coresecret" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized core"}`))
			return
		}
		if r.Header.Get("X-Request-ID") == "" {
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":"missing request id"}`))
			return
		}
		switch r.URL.Path {
		case "/models":
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
		case "/run_async":
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"abc123","status":"queued"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	defer core.Close()

	h, err := NewHandler(Config{
		CoreBaseURL: core.URL,
		BridgeToken: "bridge",
		CoreToken:   "coresecret",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rrModels := httptest.NewRecorder()
	reqModels := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqModels.Header.Set("Authorization", "Bearer bridge")
	reqModels.Header.Set("X-Request-ID", "custom-rid")
	h.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrModels.Code, rrModels.Body.String())
	}
	var modelList []map[string]any
	if err := json.Unmarshal(rrModels.Body.Bytes(), &modelList); err != nil {
		t.Fatalf("unmarshal model list: %v body=%s", err, rrModels.Body.String())
	}
	if len(modelList) != 1 || modelList[0]["name"] != "local" {
		t.Fatalf("unexpected model payload: %#v", modelList)
	}
	if rrModels.Header().Get("X-Request-ID") != "custom-rid" {
		t.Fatalf("expected response request id header")
	}

	rrRun := httptest.NewRecorder()
	reqRun := httptest.NewRequest(http.MethodPost, "/run_async", strings.NewReader(`{"objective":"test"}`))
	reqRun.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRun, reqRun)
	if rrRun.Code != http.StatusAccepted {
		t.Fatalf("expected 202 got %d body=%s", rrRun.Code, rrRun.Body.String())
	}
	var runPayload map[string]any
	if err := json.Unmarshal(rrRun.Body.Bytes(), &runPayload); err != nil {
		t.Fatalf("unmarshal run payload: %v", err)
	}
	if runPayload["request_id"] == "" {
		t.Fatalf("expected request_id in object payload")
	}
}

func TestRejectLargeBody(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "secret"})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	large := strings.Repeat("a", maxRequestBodyBytes+5)
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(`{"payload":"`+large+`"}`))
	req.Header.Set("Authorization", "Bearer secret")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 got %d body=%s", rr.Code, rr.Body.String())
	}
}
