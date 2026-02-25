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
	if healthy, ok := corePayload["healthy"].(bool); !ok || !healthy {
		t.Fatalf("expected core healthy true: %#v", corePayload)
	}
	bridgePayload, ok := payload["bridge"].(map[string]any)
	if !ok {
		t.Fatalf("expected bridge payload")
	}
	if _, ok := bridgePayload["revoked_sessions"]; !ok {
		t.Fatalf("expected bridge revoked_sessions field: %#v", bridgePayload)
	}
}

func TestHealthDeepFailsOnCoreUnauthorized(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"unauthorized"}`))
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
	if rr.Code != http.StatusBadGateway {
		t.Fatalf("expected 502 got %d body=%s", rr.Code, rr.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	corePayload, ok := payload["core"].(map[string]any)
	if !ok {
		t.Fatalf("expected core payload")
	}
	if healthy, ok := corePayload["healthy"].(bool); !ok || healthy {
		t.Fatalf("expected core healthy false: %#v", corePayload)
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
	lastIdempotencyKey := ""
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
		case "/dashboard/data":
			_, _ = w.Write([]byte(`{"health":{"ok":true},"jobs":[],"plans":[]}`))
		case "/run_async":
			lastIdempotencyKey = r.Header.Get("Idempotency-Key")
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"abc123","status":"queued"}`))
		case "/jobs/abc123/cancel":
			_, _ = w.Write([]byte(`{"id":"abc123","status":"canceled","canceled":true}`))
		case "/jobs/abc123/stream":
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: job\ndata: {\"id\":\"abc123\",\"status\":\"running\"}\n\n"))
		case "/plans/plan1/stream":
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: plan\ndata: {\"id\":\"plan1\",\"status\":\"pending\"}\n\n"))
		case "/events":
			_, _ = w.Write([]byte(`[{"id":1,"category":"run","action":"run_async"}]`))
		case "/events/stream":
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: audit\ndata: {\"id\":1,\"category\":\"run\"}\n\n"))
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
		case "/plans/plan1/approve_async":
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"plan-job-1","status":"queued","kind":"plan_approval"}`))
		case "/plans/plan1/retry_failed":
			_, _ = w.Write([]byte(`{"id":"plan1","status":"executed"}`))
		case "/plans/plan1/retry_failed_async":
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"job_id":"plan-job-retry-1","status":"queued","kind":"plan_retry_failed"}`))
		case "/plans/plan1/reject":
			_, _ = w.Write([]byte(`{"id":"plan1","status":"rejected"}`))
		case "/plans/plan1/undo":
			_, _ = w.Write([]byte(`{"plan_id":"plan1","results":[{"id":1,"ok":true}]}`))
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

	rrDashboardData := httptest.NewRecorder()
	reqDashboardData := httptest.NewRequest(http.MethodGet, "/dashboard/data", nil)
	reqDashboardData.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrDashboardData, reqDashboardData)
	if rrDashboardData.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrDashboardData.Code, rrDashboardData.Body.String())
	}
	var dashboardPayload map[string]any
	if err := json.Unmarshal(rrDashboardData.Body.Bytes(), &dashboardPayload); err != nil {
		t.Fatalf("unmarshal dashboard payload: %v", err)
	}
	healthPayload, ok := dashboardPayload["health"].(map[string]any)
	if !ok || healthPayload["ok"] != true {
		t.Fatalf("unexpected dashboard payload: %#v", dashboardPayload)
	}

	rrRun := httptest.NewRecorder()
	reqRun := httptest.NewRequest(http.MethodPost, "/run_async", strings.NewReader(`{"objective":"test"}`))
	reqRun.Header.Set("Authorization", "Bearer bridge")
	reqRun.Header.Set("Idempotency-Key", "idem-bridge-1")
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
	if lastIdempotencyKey != "idem-bridge-1" {
		t.Fatalf("expected idempotency key forwarded, got %q", lastIdempotencyKey)
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

	rrStream := httptest.NewRecorder()
	reqStream := httptest.NewRequest(http.MethodGet, "/jobs/abc123/stream", nil)
	reqStream.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrStream, reqStream)
	if rrStream.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrStream.Code, rrStream.Body.String())
	}
	if !strings.Contains(rrStream.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatalf("expected event-stream content type, got %s", rrStream.Header().Get("Content-Type"))
	}
	if !strings.Contains(rrStream.Body.String(), "event: job") {
		t.Fatalf("expected stream payload, got %s", rrStream.Body.String())
	}

	rrPlanStream := httptest.NewRecorder()
	reqPlanStream := httptest.NewRequest(http.MethodGet, "/plans/plan1/stream", nil)
	reqPlanStream.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrPlanStream, reqPlanStream)
	if rrPlanStream.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrPlanStream.Code, rrPlanStream.Body.String())
	}
	if !strings.Contains(rrPlanStream.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatalf("expected event-stream content type, got %s", rrPlanStream.Header().Get("Content-Type"))
	}
	if !strings.Contains(rrPlanStream.Body.String(), "event: plan") {
		t.Fatalf("expected plan stream payload, got %s", rrPlanStream.Body.String())
	}

	rrEvents := httptest.NewRecorder()
	reqEvents := httptest.NewRequest(http.MethodGet, "/events?limit=5", nil)
	reqEvents.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrEvents, reqEvents)
	if rrEvents.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrEvents.Code, rrEvents.Body.String())
	}

	rrEventsStream := httptest.NewRecorder()
	reqEventsStream := httptest.NewRequest(http.MethodGet, "/events/stream?timeout=1&interval=0.1&since_id=0", nil)
	reqEventsStream.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrEventsStream, reqEventsStream)
	if rrEventsStream.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrEventsStream.Code, rrEventsStream.Body.String())
	}
	if !strings.Contains(rrEventsStream.Body.String(), "event: audit") {
		t.Fatalf("expected audit stream payload, got %s", rrEventsStream.Body.String())
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

	rrApprovePlanAsync := httptest.NewRecorder()
	reqApprovePlanAsync := httptest.NewRequest(http.MethodPost, "/plans/plan1/approve_async", strings.NewReader(`{"execute":true}`))
	reqApprovePlanAsync.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrApprovePlanAsync, reqApprovePlanAsync)
	if rrApprovePlanAsync.Code != http.StatusAccepted {
		t.Fatalf("expected 202 got %d body=%s", rrApprovePlanAsync.Code, rrApprovePlanAsync.Body.String())
	}

	rrRetryFailedPlan := httptest.NewRecorder()
	reqRetryFailedPlan := httptest.NewRequest(
		http.MethodPost,
		"/plans/plan1/retry_failed",
		strings.NewReader(`{"allow_dangerous":true}`),
	)
	reqRetryFailedPlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRetryFailedPlan, reqRetryFailedPlan)
	if rrRetryFailedPlan.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrRetryFailedPlan.Code, rrRetryFailedPlan.Body.String())
	}

	rrRetryFailedPlanAsync := httptest.NewRecorder()
	reqRetryFailedPlanAsync := httptest.NewRequest(
		http.MethodPost,
		"/plans/plan1/retry_failed_async",
		strings.NewReader(`{"allow_dangerous":true}`),
	)
	reqRetryFailedPlanAsync.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRetryFailedPlanAsync, reqRetryFailedPlanAsync)
	if rrRetryFailedPlanAsync.Code != http.StatusAccepted {
		t.Fatalf("expected 202 got %d body=%s", rrRetryFailedPlanAsync.Code, rrRetryFailedPlanAsync.Body.String())
	}

	rrRejectPlan := httptest.NewRecorder()
	reqRejectPlan := httptest.NewRequest(http.MethodPost, "/plans/plan1/reject", strings.NewReader(`{"reason":"nope"}`))
	reqRejectPlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRejectPlan, reqRejectPlan)
	if rrRejectPlan.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrRejectPlan.Code, rrRejectPlan.Body.String())
	}

	rrUndoPlan := httptest.NewRecorder()
	reqUndoPlan := httptest.NewRequest(http.MethodPost, "/plans/plan1/undo", strings.NewReader(`{"mark_only":true}`))
	reqUndoPlan.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrUndoPlan, reqUndoPlan)
	if rrUndoPlan.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rrUndoPlan.Code, rrUndoPlan.Body.String())
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
	if !strings.Contains(metrics, "novaadapt_bridge_rate_limited_total") {
		t.Fatalf("expected rate limited metric, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_session_issued_total") {
		t.Fatalf("expected session issued metric, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_session_revoked_total") {
		t.Fatalf("expected session revoked metric, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_ws_rejected_total") {
		t.Fatalf("expected ws rejected metric, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_ws_active_connections") {
		t.Fatalf("expected ws active connections metric, got: %s", metrics)
	}
}

func TestDeviceAllowlist(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:      core.URL,
			BridgeToken:      "secret",
			AllowedDeviceIDs: []string{"iphone-1", "halo-1"},
			Timeout:          5 * time.Second,
			LogRequests:      false,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rrMissing := httptest.NewRecorder()
	reqMissing := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqMissing.Header.Set("Authorization", "Bearer secret")
	h.ServeHTTP(rrMissing, reqMissing)
	if rrMissing.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for missing device id, got %d", rrMissing.Code)
	}

	rrWrong := httptest.NewRecorder()
	reqWrong := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqWrong.Header.Set("Authorization", "Bearer secret")
	reqWrong.Header.Set("X-Device-ID", "unknown")
	h.ServeHTTP(rrWrong, reqWrong)
	if rrWrong.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for unknown device id, got %d", rrWrong.Code)
	}

	rrAllowed := httptest.NewRecorder()
	reqAllowed := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqAllowed.Header.Set("Authorization", "Bearer secret")
	reqAllowed.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrAllowed, reqAllowed)
	if rrAllowed.Code != http.StatusOK {
		t.Fatalf("expected 200 for allowed device id, got %d body=%s", rrAllowed.Code, rrAllowed.Body.String())
	}
}

func TestCORSPreflightAllowedOrigin(t *testing.T) {
	h, err := NewHandler(
		Config{
			CoreBaseURL:        "http://example.com",
			BridgeToken:        "secret",
			CORSAllowedOrigins: []string{"http://127.0.0.1:8088"},
			Timeout:            5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodOptions, "/auth/session", nil)
	req.Host = "127.0.0.1:9797"
	req.Header.Set("Origin", "http://127.0.0.1:8088")
	req.Header.Set("Access-Control-Request-Method", "POST")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("expected 204 got %d body=%s", rr.Code, rr.Body.String())
	}
	if rr.Header().Get("Access-Control-Allow-Origin") != "http://127.0.0.1:8088" {
		t.Fatalf("expected allow origin header, got %s", rr.Header().Get("Access-Control-Allow-Origin"))
	}
	if !strings.Contains(rr.Header().Get("Access-Control-Allow-Methods"), "POST") {
		t.Fatalf("expected POST allowed method, got %s", rr.Header().Get("Access-Control-Allow-Methods"))
	}
}

func TestCORSBlocksDisallowedOrigin(t *testing.T) {
	h, err := NewHandler(
		Config{
			CoreBaseURL:        "http://example.com",
			BridgeToken:        "secret",
			CORSAllowedOrigins: []string{"http://127.0.0.1:8088"},
			Timeout:            5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Host = "127.0.0.1:9797"
	req.Header.Set("Origin", "http://evil.example")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403 got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestCORSSameOriginAllowedWithoutConfig(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "secret", Timeout: 5 * time.Second})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Host = "bridge.local:9797"
	req.Header.Set("Origin", "http://bridge.local:9797")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestCORSSpoofedForwardedProtoDeniedWithoutTrustedProxy(t *testing.T) {
	h, err := NewHandler(Config{CoreBaseURL: "http://example.com", BridgeToken: "secret", Timeout: 5 * time.Second})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Host = "bridge.local:9797"
	req.RemoteAddr = "203.0.113.10:1234"
	req.Header.Set("Origin", "https://bridge.local:9797")
	req.Header.Set("X-Forwarded-Proto", "https")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403 got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestCORSSameOriginViaTrustedProxyForwardedProtoAllowed(t *testing.T) {
	h, err := NewHandler(
		Config{
			CoreBaseURL:       "http://example.com",
			BridgeToken:       "secret",
			TrustedProxyCIDRs: []string{"203.0.113.0/24"},
			Timeout:           5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Host = "bridge.local:9797"
	req.RemoteAddr = "203.0.113.10:1234"
	req.Header.Set("Origin", "https://bridge.local:9797")
	req.Header.Set("X-Forwarded-Proto", "https")
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestRateLimitPerClient(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:    core.URL,
			BridgeToken:    "secret",
			RateLimitRPS:   1.0,
			RateLimitBurst: 1,
			Timeout:        5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	first := httptest.NewRecorder()
	reqFirst := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqFirst.Header.Set("Authorization", "Bearer secret")
	reqFirst.RemoteAddr = "203.0.113.10:1234"
	h.ServeHTTP(first, reqFirst)
	if first.Code != http.StatusOK {
		t.Fatalf("expected first request 200 got %d body=%s", first.Code, first.Body.String())
	}

	second := httptest.NewRecorder()
	reqSecond := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqSecond.Header.Set("Authorization", "Bearer secret")
	reqSecond.RemoteAddr = "203.0.113.10:1234"
	h.ServeHTTP(second, reqSecond)
	if second.Code != http.StatusTooManyRequests {
		t.Fatalf("expected second request 429 got %d body=%s", second.Code, second.Body.String())
	}
	if second.Header().Get("Retry-After") != "1" {
		t.Fatalf("expected retry-after header on rate-limited response")
	}

	otherClient := httptest.NewRecorder()
	reqOtherClient := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqOtherClient.Header.Set("Authorization", "Bearer secret")
	reqOtherClient.RemoteAddr = "203.0.113.11:5678"
	h.ServeHTTP(otherClient, reqOtherClient)
	if otherClient.Code != http.StatusOK {
		t.Fatalf("expected different client to pass rate limit, got %d body=%s", otherClient.Code, otherClient.Body.String())
	}
}

func TestRateLimitDoesNotTrustForwardedForByDefault(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:    core.URL,
			BridgeToken:    "secret",
			RateLimitRPS:   1.0,
			RateLimitBurst: 1,
			Timeout:        5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	first := httptest.NewRecorder()
	reqFirst := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqFirst.Header.Set("Authorization", "Bearer secret")
	reqFirst.Header.Set("X-Forwarded-For", "198.51.100.50")
	reqFirst.RemoteAddr = "203.0.113.10:1234"
	h.ServeHTTP(first, reqFirst)
	if first.Code != http.StatusOK {
		t.Fatalf("expected first request 200 got %d body=%s", first.Code, first.Body.String())
	}

	second := httptest.NewRecorder()
	reqSecond := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqSecond.Header.Set("Authorization", "Bearer secret")
	reqSecond.Header.Set("X-Forwarded-For", "198.51.100.50")
	reqSecond.RemoteAddr = "203.0.113.11:5678"
	h.ServeHTTP(second, reqSecond)
	if second.Code != http.StatusOK {
		t.Fatalf("expected second request from different socket client to pass, got %d body=%s", second.Code, second.Body.String())
	}
}

func TestRateLimitTrustsForwardedForFromTrustedProxy(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL:       core.URL,
			BridgeToken:       "secret",
			TrustedProxyCIDRs: []string{"203.0.113.0/24"},
			RateLimitRPS:      1.0,
			RateLimitBurst:    1,
			Timeout:           5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	first := httptest.NewRecorder()
	reqFirst := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqFirst.Header.Set("Authorization", "Bearer secret")
	reqFirst.Header.Set("X-Forwarded-For", "198.51.100.77")
	reqFirst.RemoteAddr = "203.0.113.10:1234"
	h.ServeHTTP(first, reqFirst)
	if first.Code != http.StatusOK {
		t.Fatalf("expected first request 200 got %d body=%s", first.Code, first.Body.String())
	}

	second := httptest.NewRecorder()
	reqSecond := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqSecond.Header.Set("Authorization", "Bearer secret")
	reqSecond.Header.Set("X-Forwarded-For", "198.51.100.77")
	reqSecond.RemoteAddr = "203.0.113.11:5678"
	h.ServeHTTP(second, reqSecond)
	if second.Code != http.StatusTooManyRequests {
		t.Fatalf("expected second request 429 due to shared forwarded client IP, got %d body=%s", second.Code, second.Body.String())
	}
}

func TestInvalidTrustedProxyCIDRRejected(t *testing.T) {
	_, err := NewHandler(Config{
		CoreBaseURL:       "http://example.com",
		BridgeToken:       "secret",
		TrustedProxyCIDRs: []string{"not-a-cidr"},
	})
	if err == nil {
		t.Fatalf("expected invalid trusted proxy cidr to fail handler init")
	}
}
