package relay

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"path"
	"strings"
	"sync/atomic"
	"time"
)

const maxRequestBodyBytes = 1 << 20 // 1 MiB

var allowedPaths = map[string]struct{}{
	"/models":         {},
	"/openapi.json":   {},
	"/dashboard":      {},
	"/dashboard/data": {},
	"/history":        {},
	"/run":            {},
	"/run_async":      {},
	"/undo":           {},
	"/check":          {},
	"/jobs":           {},
	"/plans":          {},
	"/events":         {},
}

// Config controls bridge relay behavior.
type Config struct {
	CoreBaseURL string
	BridgeToken string
	CoreToken   string
	Timeout     time.Duration
	LogRequests bool
	Logger      *log.Logger
}

// Handler is an HTTP handler that secures and forwards requests to NovaAdapt core.
type Handler struct {
	cfg    Config
	client *http.Client

	requestsTotal       uint64
	unauthorizedTotal   uint64
	upstreamErrorsTotal uint64
}

// NewHandler creates a configured bridge relay handler.
func NewHandler(cfg Config) (*Handler, error) {
	if strings.TrimSpace(cfg.CoreBaseURL) == "" {
		return nil, fmt.Errorf("core base url is required")
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 30 * time.Second
	}
	if cfg.Logger == nil {
		cfg.Logger = log.Default()
	}
	_, err := url.Parse(cfg.CoreBaseURL)
	if err != nil {
		return nil, fmt.Errorf("invalid core base url: %w", err)
	}
	return &Handler{
		cfg: cfg,
		client: &http.Client{
			Timeout: cfg.Timeout,
		},
	}, nil
}

// ServeHTTP handles bridge requests.
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	atomic.AddUint64(&h.requestsTotal, 1)

	started := time.Now()
	requestID := normalizeRequestID(r.Header.Get("X-Request-ID"))
	w.Header().Set("X-Request-ID", requestID)

	statusCode := http.StatusOK
	defer func() {
		if h.cfg.LogRequests {
			h.cfg.Logger.Printf(
				"bridge request id=%s method=%s path=%s status=%d duration_ms=%.2f",
				requestID,
				r.Method,
				r.URL.Path,
				statusCode,
				float64(time.Since(started).Microseconds())/1000.0,
			)
		}
	}()

	if r.URL.Path == "/health" {
		statusCode, payload := h.healthPayload(requestID, r.URL.Query().Get("deep") == "1")
		h.writeJSON(w, statusCode, payload)
		return
	}

	if r.URL.Path == "/metrics" {
		statusCode = http.StatusOK
		h.writeMetrics(w)
		return
	}

	if !h.authorized(r) {
		atomic.AddUint64(&h.unauthorizedTotal, 1)
		statusCode = http.StatusUnauthorized
		h.writeJSONWithStatus(
			w,
			statusCode,
			map[string]any{"error": "Unauthorized", "request_id": requestID},
			true,
		)
		return
	}

	if r.URL.Path == "/ws" {
		statusCode = h.handleWebSocket(w, r, requestID)
		if statusCode >= 500 {
			atomic.AddUint64(&h.upstreamErrorsTotal, 1)
		}
		return
	}

	if !isForwardedPath(r.URL.Path) {
		statusCode = http.StatusNotFound
		h.writeJSON(w, statusCode, map[string]any{"error": "Not found", "request_id": requestID})
		return
	}

	if isRawForwardPath(r.URL.Path) {
		if r.Method != http.MethodGet {
			statusCode = http.StatusMethodNotAllowed
			h.writeJSON(w, statusCode, map[string]any{"error": "Method not allowed", "request_id": requestID})
			return
		}
		rawStatus, rawContentType, rawBody := h.forwardRaw(r, requestID)
		statusCode = rawStatus
		if rawStatus >= 500 {
			atomic.AddUint64(&h.upstreamErrorsTotal, 1)
		}
		h.writeRaw(w, rawStatus, rawContentType, rawBody)
		return
	}

	if r.Method != http.MethodGet && r.Method != http.MethodPost {
		statusCode = http.StatusMethodNotAllowed
		h.writeJSON(w, statusCode, map[string]any{"error": "Method not allowed", "request_id": requestID})
		return
	}

	body, err := h.readBody(r)
	if err != nil {
		statusCode = http.StatusBadRequest
		h.writeJSON(w, statusCode, map[string]any{"error": err.Error(), "request_id": requestID})
		return
	}

	statusCode, payload := h.forward(r, requestID, body)
	if statusCode >= 500 {
		atomic.AddUint64(&h.upstreamErrorsTotal, 1)
	}
	h.writeJSON(w, statusCode, payload)
}

func (h *Handler) healthPayload(requestID string, deep bool) (int, any) {
	payload := map[string]any{
		"ok":         true,
		"service":    "novaadapt-bridge-go",
		"request_id": requestID,
	}
	if !deep {
		return http.StatusOK, payload
	}

	target, err := joinURL(h.cfg.CoreBaseURL, "/health", "")
	if err != nil {
		payload["ok"] = false
		payload["core"] = map[string]any{"reachable": false, "error": "invalid core URL"}
		return http.StatusBadGateway, payload
	}
	req, err := http.NewRequest(http.MethodGet, target, nil)
	if err != nil {
		payload["ok"] = false
		payload["core"] = map[string]any{"reachable": false, "error": "failed to create request"}
		return http.StatusBadGateway, payload
	}
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}
	resp, err := h.client.Do(req)
	if err != nil {
		payload["ok"] = false
		payload["core"] = map[string]any{"reachable": false, "error": err.Error()}
		return http.StatusBadGateway, payload
	}
	defer resp.Body.Close()
	payload["core"] = map[string]any{"reachable": resp.StatusCode < 500, "status": resp.StatusCode}
	if resp.StatusCode >= 500 {
		payload["ok"] = false
		return http.StatusBadGateway, payload
	}
	return http.StatusOK, payload
}

func isForwardedPath(p string) bool {
	if strings.HasPrefix(p, "/jobs/") {
		id := strings.TrimSpace(strings.TrimPrefix(p, "/jobs/"))
		return id != ""
	}
	if p == "/events/stream" {
		return true
	}
	if strings.HasPrefix(p, "/plans/") {
		id := strings.TrimSpace(strings.TrimPrefix(p, "/plans/"))
		return id != ""
	}
	_, ok := allowedPaths[p]
	return ok
}

func isRawForwardPath(p string) bool {
	if p == "/dashboard" {
		return true
	}
	if strings.HasPrefix(p, "/jobs/") && strings.HasSuffix(p, "/stream") {
		return true
	}
	if p == "/events/stream" {
		return true
	}
	return strings.HasPrefix(p, "/plans/") && strings.HasSuffix(p, "/stream")
}

func (h *Handler) authorized(r *http.Request) bool {
	if strings.TrimSpace(h.cfg.BridgeToken) == "" {
		return true
	}
	expected := "Bearer " + h.cfg.BridgeToken
	return r.Header.Get("Authorization") == expected
}

func (h *Handler) readBody(r *http.Request) ([]byte, error) {
	if r.Method != http.MethodPost {
		return nil, nil
	}
	if r.Body == nil {
		return []byte("{}"), nil
	}
	defer r.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxRequestBodyBytes+1))
	if err != nil {
		return nil, fmt.Errorf("failed to read request body")
	}
	if len(raw) > maxRequestBodyBytes {
		return nil, fmt.Errorf("request body too large")
	}
	if len(bytes.TrimSpace(raw)) == 0 {
		return []byte("{}"), nil
	}
	var tmp map[string]any
	if err := json.Unmarshal(raw, &tmp); err != nil {
		return nil, fmt.Errorf("request body must be valid JSON object")
	}
	return raw, nil
}

func (h *Handler) forward(r *http.Request, requestID string, body []byte) (int, any) {
	target, err := joinURL(h.cfg.CoreBaseURL, r.URL.Path, r.URL.RawQuery)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to build core URL", "request_id": requestID}
	}

	var reqBody io.Reader
	if r.Method == http.MethodPost {
		reqBody = bytes.NewReader(body)
	}

	req, err := http.NewRequest(r.Method, target, reqBody)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to create core request", "request_id": requestID}
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", requestID)
	if idem := strings.TrimSpace(r.Header.Get("Idempotency-Key")); idem != "" {
		req.Header.Set("Idempotency-Key", idem)
	}
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": fmt.Sprintf("Core API unreachable: %v", err), "request_id": requestID}
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to read core response", "request_id": requestID}
	}

	payload, ok := decodeAnyJSON(raw)
	if !ok {
		payload = map[string]any{"raw": string(raw), "request_id": requestID}
	} else {
		payload = attachRequestID(payload, requestID)
	}

	return resp.StatusCode, payload
}

func (h *Handler) forwardRaw(r *http.Request, requestID string) (int, string, []byte) {
	target, err := joinURL(h.cfg.CoreBaseURL, r.URL.Path, r.URL.RawQuery)
	if err != nil {
		payload, _ := json.Marshal(map[string]any{"error": "Failed to build core URL", "request_id": requestID})
		return http.StatusBadGateway, "application/json", payload
	}
	req, err := http.NewRequest(http.MethodGet, target, nil)
	if err != nil {
		payload, _ := json.Marshal(map[string]any{"error": "Failed to create core request", "request_id": requestID})
		return http.StatusBadGateway, "application/json", payload
	}
	req.Header.Set("X-Request-ID", requestID)
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}
	resp, err := h.client.Do(req)
	if err != nil {
		payload, _ := json.Marshal(map[string]any{"error": fmt.Sprintf("Core API unreachable: %v", err), "request_id": requestID})
		return http.StatusBadGateway, "application/json", payload
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		payload, _ := json.Marshal(map[string]any{"error": "Failed to read core response", "request_id": requestID})
		return http.StatusBadGateway, "application/json", payload
	}
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "text/html; charset=utf-8"
	}
	return resp.StatusCode, contentType, body
}

func joinURL(base, requestPath, rawQuery string) (string, error) {
	u, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	u.Path = path.Join(u.Path, requestPath)
	u.RawQuery = rawQuery
	return u.String(), nil
}

func decodeAnyJSON(raw []byte) (any, bool) {
	if len(bytes.TrimSpace(raw)) == 0 {
		return map[string]any{}, true
	}
	var payload any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, false
	}
	return payload, true
}

func attachRequestID(payload any, requestID string) any {
	if obj, ok := payload.(map[string]any); ok {
		if _, exists := obj["request_id"]; !exists {
			obj["request_id"] = requestID
		}
		return obj
	}
	return payload
}

func normalizeRequestID(current string) string {
	id := strings.TrimSpace(current)
	if id != "" {
		return id
	}
	buf := make([]byte, 12)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("rid-%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(buf)
}

func (h *Handler) writeJSON(w http.ResponseWriter, status int, payload any) {
	h.writeJSONWithStatus(w, status, payload, false)
}

func (h *Handler) writeJSONWithStatus(w http.ResponseWriter, status int, payload any, unauthorized bool) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		encoded = []byte(`{"error":"failed to encode response"}`)
		status = http.StatusInternalServerError
	}
	w.Header().Set("Content-Type", "application/json")
	if unauthorized {
		w.Header().Set("WWW-Authenticate", "Bearer")
	}
	w.WriteHeader(status)
	_, _ = w.Write(encoded)
}

func (h *Handler) writeMetrics(w http.ResponseWriter) {
	body := fmt.Sprintf(
		"novaadapt_bridge_requests_total %d\n"+
			"novaadapt_bridge_unauthorized_total %d\n"+
			"novaadapt_bridge_upstream_errors_total %d\n",
		atomic.LoadUint64(&h.requestsTotal),
		atomic.LoadUint64(&h.unauthorizedTotal),
		atomic.LoadUint64(&h.upstreamErrorsTotal),
	)
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	_, _ = w.Write([]byte(body))
}

func (h *Handler) writeRaw(w http.ResponseWriter, status int, contentType string, body []byte) {
	w.Header().Set("Content-Type", contentType)
	w.WriteHeader(status)
	_, _ = w.Write(body)
}
