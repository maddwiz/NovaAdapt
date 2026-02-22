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
		case "/openapi.json":
			_, _ = w.Write([]byte(`{"openapi":"3.1.0","paths":{"/run":{}}}`))
		case "/dashboard":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			_, _ = w.Write([]byte(`<html><body>dashboard</body></html>`))
		case "/run_async":
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"abc123","status":"queued"}`))
		case "/jobs/abc123/cancel":
			_, _ = w.Write([]byte(`{"id":"abc123","status":"canceled","canceled":true}`))
		case "/plans":
			if r.Method == http.MethodGet {
				_, _ = w.Write([]byte(`[{"id":"plan1","status":"pending"}]`))
				return
			}
			w.WriteHeader(http.StatusCreated)
			_, _ = w.Write([]byte(`{"id":"plan1","status":"pending"}`))
		case "/plans/plan1":
			_, _ = w.Write([]byte(`{"id":"plan1","status":"pending"}`))
		case "/plans/plan1/approve":
			_, _ = w.Write([]byte(`{"id":"plan1","status":"executed"}`))
		case "/plans/plan1/reject":
			_, _ = w.Write([]byte(`{"id":"plan1","status":"rejected"}`))
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

	rrOpenAPI := httptest.NewRecorder()
	reqOpenAPI := httptest.NewRequest(http.MethodGet, "/openapi.json", nil)
	reqOpenAPI.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrOpenAPI, reqOpenAPI)
	if rrOpenAPI.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrOpenAPI.Code, rrOpenAPI.Body.String())
	}
	var spec map[string]any
	if err := json.Unmarshal(rrOpenAPI.Body.Bytes(), &spec); err != nil {
		t.Fatalf("unmarshal spec: %v", err)
	}
	if spec["openapi"] != "3.1.0" {
		t.Fatalf("unexpected spec payload: %#v", spec)
	}

	rrDashboard := httptest.NewRecorder()
	reqDashboard := httptest.NewRequest(http.MethodGet, "/dashboard", nil)
	reqDashboard.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrDashboard, reqDashboard)
	if rrDashboard.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrDashboard.Code, rrDashboard.Body.String())
	}
	if !strings.Contains(rrDashboard.Body.String(), "dashboard") {
		t.Fatalf("expected dashboard body, got %s", rrDashboard.Body.String())
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

	rrCancel := httptest.NewRecorder()
	reqCancel := httptest.NewRequest(http.MethodPost, "/jobs/abc123/cancel", strings.NewReader(`{}`))
	reqCancel.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrCancel, reqCancel)
	if rrCancel.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrCancel.Code, rrCancel.Body.String())
	}
	var cancelPayload map[string]any
	if err := json.Unmarshal(rrCancel.Body.Bytes(), &cancelPayload); err != nil {
		t.Fatalf("unmarshal cancel payload: %v", err)
	}
	if cancelPayload["id"] != "abc123" {
		t.Fatalf("unexpected cancel payload: %#v", cancelPayload)
	}

	rrPlans := httptest.NewRecorder()
	reqPlans := httptest.NewRequest(http.MethodGet, "/plans", nil)
	reqPlans.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrPlans, reqPlans)
	if rrPlans.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrPlans.Code, rrPlans.Body.String())
	}

	rrCreatePlan := httptest.NewRecorder()
	reqCreatePlan := httptest.NewRequest(http.MethodPost, "/plans", strings.NewReader(`{"objective":"test"}`))
	reqCreatePlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrCreatePlan, reqCreatePlan)
	if rrCreatePlan.Code != http.StatusCreated {
		t.Fatalf("expected 201 got %d body=%s", rrCreatePlan.Code, rrCreatePlan.Body.String())
	}

	rrApprovePlan := httptest.NewRecorder()
	reqApprovePlan := httptest.NewRequest(http.MethodPost, "/plans/plan1/approve", strings.NewReader(`{"execute":true}`))
	reqApprovePlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrApprovePlan, reqApprovePlan)
	if rrApprovePlan.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrApprovePlan.Code, rrApprovePlan.Body.String())
	}

	rrRejectPlan := httptest.NewRecorder()
	reqRejectPlan := httptest.NewRequest(http.MethodPost, "/plans/plan1/reject", strings.NewReader(`{"reason":"nope"}`))
	reqRejectPlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRejectPlan, reqRejectPlan)
	if rrRejectPlan.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrRejectPlan.Code, rrRejectPlan.Body.String())
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

func TestMetricsEndpoint(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/models":
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	defer core.Close()

	h, err := NewHandler(Config{CoreBaseURL: core.URL, BridgeToken: "secret", Timeout: 5 * time.Second})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	// Unauthorized request increments unauthorized counter.
	rrUnauth := httptest.NewRecorder()
	reqUnauth := httptest.NewRequest(http.MethodGet, "/models", nil)
	h.ServeHTTP(rrUnauth, reqUnauth)
	if rrUnauth.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 got %d", rrUnauth.Code)
	}

	// Authorized request increments total counter.
	rrAuth := httptest.NewRecorder()
	reqAuth := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqAuth.Header.Set("Authorization", "Bearer secret")
	h.ServeHTTP(rrAuth, reqAuth)
	if rrAuth.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d", rrAuth.Code)
	}

	rrMetrics := httptest.NewRecorder()
	reqMetrics := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	h.ServeHTTP(rrMetrics, reqMetrics)
	if rrMetrics.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d", rrMetrics.Code)
	}
	metrics := rrMetrics.Body.String()
	if !strings.Contains(metrics, "novaadapt_bridge_requests_total") {
		t.Fatalf("expected requests metric, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_unauthorized_total") {
		t.Fatalf("expected unauthorized metric, got: %s", metrics)
	}
}
