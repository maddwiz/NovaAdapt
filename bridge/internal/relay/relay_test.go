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

func TestForwardWithAuth(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer coresecret" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized core"}`))
			return
		}
		switch r.URL.Path {
		case "/models":
			_, _ = w.Write([]byte(`{"name":"local"}`))
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
	h.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrModels.Code, rrModels.Body.String())
	}
	var model map[string]any
	if err := json.Unmarshal(rrModels.Body.Bytes(), &model); err != nil {
		t.Fatalf("unmarshal model: %v", err)
	}
	if model["name"] != "local" {
		t.Fatalf("unexpected model payload: %#v", model)
	}

	rrRun := httptest.NewRecorder()
	reqRun := httptest.NewRequest(http.MethodPost, "/run_async", strings.NewReader(`{"objective":"test"}`))
	reqRun.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRun, reqRun)
	if rrRun.Code != http.StatusAccepted {
		t.Fatalf("expected 202 got %d body=%s", rrRun.Code, rrRun.Body.String())
	}
}
