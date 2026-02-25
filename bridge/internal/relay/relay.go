package relay

import (
	"bytes"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/time/rate"
)

const maxRequestBodyBytes = 1 << 20 // 1 MiB

const rateLimiterIdleTTL = 15 * time.Minute

type clientLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

type corsState int

const (
	corsNotApplicable corsState = iota
	corsAllowed
	corsDenied
)

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
	// CoreCAFile optionally sets a CA bundle PEM file for bridge->core TLS verification.
	CoreCAFile string
	// CoreClientCertFile and CoreClientKeyFile optionally enable mTLS client cert auth to core.
	CoreClientCertFile string
	CoreClientKeyFile  string
	// CoreTLSServerName overrides SNI/hostname verification for bridge->core TLS.
	CoreTLSServerName string
	// CoreTLSInsecureSkipVerify disables core certificate verification. Only for local/dev use.
	CoreTLSInsecureSkipVerify bool
	// SessionSigningKey signs scoped short-lived session tokens for websocket/browser clients.
	SessionSigningKey string
	// SessionTokenTTL controls default issued session token lifetime.
	SessionTokenTTL time.Duration
	// AllowedDeviceIDs optionally restricts requests to known device IDs via X-Device-ID.
	// Empty means device allowlisting is disabled.
	AllowedDeviceIDs []string
	// CORSAllowedOrigins controls which browser origins may call cross-origin bridge APIs.
	// Empty keeps cross-origin requests blocked; same-origin requests are always allowed.
	CORSAllowedOrigins []string
	// TrustedProxyCIDRs defines which remote client networks are allowed to set
	// X-Forwarded-For / X-Forwarded-Proto headers.
	TrustedProxyCIDRs []string
	// RevocationStorePath optionally persists revoked session IDs across bridge restarts.
	RevocationStorePath string
	// RateLimitRPS limits requests per client key (remote IP / forwarded IP). <=0 disables.
	RateLimitRPS float64
	// RateLimitBurst configures token bucket burst size when RateLimitRPS is enabled.
	RateLimitBurst int
	// MaxWSConnections limits concurrent websocket sessions. 0 disables limit.
	MaxWSConnections int
	Timeout          time.Duration
	LogRequests      bool
	Logger           *log.Logger
}

// Handler is an HTTP handler that secures and forwards requests to NovaAdapt core.
type Handler struct {
	cfg    Config
	client *http.Client

	requestsTotal       uint64
	unauthorizedTotal   uint64
	upstreamErrorsTotal uint64
	rateLimitedTotal    uint64
	sessionIssuedTotal  uint64
	sessionRevokedTotal uint64
	wsRejectedTotal     uint64
	wsActiveConnections int64
	allowedDevices      map[string]struct{}
	corsAllowedOrigins  map[string]struct{}
	corsAllowAll        bool
	trustedProxies      []*net.IPNet
	revokedSessionsMu   sync.RWMutex
	revokedSessions     map[string]int64
	rateLimitMu         sync.Mutex
	rateLimiters        map[string]*clientLimiter
}

// NewHandler creates a configured bridge relay handler.
func NewHandler(cfg Config) (*Handler, error) {
	if strings.TrimSpace(cfg.CoreBaseURL) == "" {
		return nil, fmt.Errorf("core base url is required")
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 30 * time.Second
	}
	if cfg.RateLimitBurst <= 0 {
		cfg.RateLimitBurst = 20
	}
	if cfg.MaxWSConnections < 0 {
		cfg.MaxWSConnections = 0
	}
	if cfg.MaxWSConnections == 0 {
		cfg.MaxWSConnections = 100
	}
	if cfg.SessionTokenTTL <= 0 {
		cfg.SessionTokenTTL = 15 * time.Minute
	}
	if cfg.Logger == nil {
		cfg.Logger = log.Default()
	}
	coreURL, err := url.Parse(strings.TrimSpace(cfg.CoreBaseURL))
	if err != nil {
		return nil, fmt.Errorf("invalid core base url: %w", err)
	}
	if coreURL.Scheme != "http" && coreURL.Scheme != "https" {
		return nil, fmt.Errorf("core base url must use http or https")
	}
	coreClient, err := buildCoreHTTPClient(cfg, coreURL.Scheme == "https")
	if err != nil {
		return nil, err
	}
	allowedDevices := make(map[string]struct{})
	for _, item := range cfg.AllowedDeviceIDs {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		allowedDevices[trimmed] = struct{}{}
	}
	corsAllowedOrigins := make(map[string]struct{})
	corsAllowAll := false
	for _, item := range cfg.CORSAllowedOrigins {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		if trimmed == "*" {
			corsAllowAll = true
			continue
		}
		corsAllowedOrigins[canonicalOrigin(trimmed)] = struct{}{}
	}
	revokedSessions, err := loadRevocationEntries(strings.TrimSpace(cfg.RevocationStorePath), time.Now().Unix())
	if err != nil {
		return nil, fmt.Errorf("failed to load revocation store: %w", err)
	}
	trustedProxies, err := parseTrustedProxyCIDRs(cfg.TrustedProxyCIDRs)
	if err != nil {
		return nil, fmt.Errorf("invalid trusted proxy cidr config: %w", err)
	}
	return &Handler{
		cfg:                cfg,
		client:             coreClient,
		allowedDevices:     allowedDevices,
		corsAllowedOrigins: corsAllowedOrigins,
		corsAllowAll:       corsAllowAll,
		trustedProxies:     trustedProxies,
		revokedSessions:    revokedSessions,
		rateLimiters:       make(map[string]*clientLimiter),
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

	corsState := h.applyCORSHeaders(w, r)
	if corsState == corsDenied {
		statusCode = http.StatusForbidden
		h.writeJSON(w, statusCode, map[string]any{"error": "CORS origin not allowed", "request_id": requestID})
		return
	}
	if r.Method == http.MethodOptions && corsState == corsAllowed {
		statusCode = http.StatusNoContent
		w.WriteHeader(statusCode)
		return
	}

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
	if h.isRateLimited(r, started) {
		atomic.AddUint64(&h.rateLimitedTotal, 1)
		statusCode = http.StatusTooManyRequests
		w.Header().Set("Retry-After", "1")
		h.writeJSON(w, statusCode, map[string]any{"error": "Rate limit exceeded", "request_id": requestID})
		return
	}

	auth := h.authenticate(r)
	if !auth.Authorized {
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

	if r.URL.Path == "/auth/session" {
		if r.Method != http.MethodPost {
			statusCode = http.StatusMethodNotAllowed
			h.writeJSON(w, statusCode, map[string]any{"error": "Method not allowed", "request_id": requestID})
			return
		}
		if !auth.hasScope(scopeAdmin) {
			statusCode = http.StatusForbidden
			h.writeJSON(w, statusCode, map[string]any{"error": "Forbidden", "request_id": requestID})
			return
		}
		body, err := h.readBody(r)
		if err != nil {
			statusCode = http.StatusBadRequest
			h.writeJSON(w, statusCode, map[string]any{"error": err.Error(), "request_id": requestID})
			return
		}
		issued, err := h.handleIssueSessionToken(body, auth, requestID)
		if err != nil {
			statusCode = http.StatusBadRequest
			h.writeJSON(w, statusCode, map[string]any{"error": err.Error(), "request_id": requestID})
			return
		}
		statusCode = http.StatusOK
		atomic.AddUint64(&h.sessionIssuedTotal, 1)
		h.writeJSON(w, statusCode, issued)
		return
	}
	if r.URL.Path == "/auth/session/revoke" {
		if r.Method != http.MethodPost {
			statusCode = http.StatusMethodNotAllowed
			h.writeJSON(w, statusCode, map[string]any{"error": "Method not allowed", "request_id": requestID})
			return
		}
		if !auth.hasScope(scopeAdmin) {
			statusCode = http.StatusForbidden
			h.writeJSON(w, statusCode, map[string]any{"error": "Forbidden", "request_id": requestID})
			return
		}
		body, err := h.readBody(r)
		if err != nil {
			statusCode = http.StatusBadRequest
			h.writeJSON(w, statusCode, map[string]any{"error": err.Error(), "request_id": requestID})
			return
		}
		revoked, err := h.handleRevokeSessionToken(body, requestID)
		if err != nil {
			statusCode = http.StatusBadRequest
			h.writeJSON(w, statusCode, map[string]any{"error": err.Error(), "request_id": requestID})
			return
		}
		statusCode = http.StatusOK
		atomic.AddUint64(&h.sessionRevokedTotal, 1)
		h.writeJSON(w, statusCode, revoked)
		return
	}

	if r.URL.Path == "/ws" {
		statusCode = h.handleWebSocket(w, r, requestID, auth)
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

	if !auth.canAccess(r.Method, r.URL.Path) {
		statusCode = http.StatusForbidden
		h.writeJSON(w, statusCode, map[string]any{"error": "Forbidden", "request_id": requestID})
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
	payload["bridge"] = h.bridgeHealthSnapshot()
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
	coreHealthy := resp.StatusCode >= 200 && resp.StatusCode < 300
	payload["core"] = map[string]any{
		"reachable": resp.StatusCode < 500,
		"status":    resp.StatusCode,
		"healthy":   coreHealthy,
	}
	if !coreHealthy {
		payload["ok"] = false
		return http.StatusBadGateway, payload
	}
	return http.StatusOK, payload
}

func (h *Handler) bridgeHealthSnapshot() map[string]any {
	h.revokedSessionsMu.RLock()
	revokedCount := len(h.revokedSessions)
	h.revokedSessionsMu.RUnlock()

	h.rateLimitMu.Lock()
	trackedClients := len(h.rateLimiters)
	h.rateLimitMu.Unlock()

	return map[string]any{
		"rate_limit_rps":        h.cfg.RateLimitRPS,
		"rate_limit_burst":      h.cfg.RateLimitBurst,
		"rate_limit_clients":    trackedClients,
		"ws_max_connections":    h.cfg.MaxWSConnections,
		"ws_active_connections": atomic.LoadInt64(&h.wsActiveConnections),
		"revoked_sessions":      revokedCount,
		"revocation_store_path": strings.TrimSpace(h.cfg.RevocationStorePath),
		"core_tls_enabled":      strings.HasPrefix(strings.ToLower(strings.TrimSpace(h.cfg.CoreBaseURL)), "https://"),
		"core_mtls_enabled":     strings.TrimSpace(h.cfg.CoreClientCertFile) != "",
	}
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

func (h *Handler) applyCORSHeaders(w http.ResponseWriter, r *http.Request) corsState {
	origin := strings.TrimSpace(r.Header.Get("Origin"))
	if origin == "" {
		return corsNotApplicable
	}
	if !h.isOriginAllowed(r, origin) {
		return corsDenied
	}
	w.Header().Set("Vary", "Origin")
	w.Header().Set("Access-Control-Allow-Origin", origin)
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Device-ID, X-Request-ID, Idempotency-Key")
	w.Header().Set("Access-Control-Expose-Headers", "X-Request-ID, Idempotency-Key, X-Idempotency-Replayed")
	w.Header().Set("Access-Control-Max-Age", "600")
	return corsAllowed
}

func (h *Handler) isOriginAllowed(r *http.Request, origin string) bool {
	if isSameOrigin(r, origin, h.requestScheme(r)) {
		return true
	}
	if h.corsAllowAll {
		return true
	}
	_, ok := h.corsAllowedOrigins[canonicalOrigin(origin)]
	return ok
}

func isSameOrigin(r *http.Request, origin string, scheme string) bool {
	expectedOrigin := scheme + "://" + r.Host
	return canonicalOrigin(origin) == canonicalOrigin(expectedOrigin)
}

func (h *Handler) requestScheme(r *http.Request) string {
	if h.isTrustedProxy(r) {
		forwarded := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto"))
		if forwarded != "" {
			if idx := strings.Index(forwarded, ","); idx >= 0 {
				forwarded = forwarded[:idx]
			}
			candidate := strings.ToLower(strings.TrimSpace(forwarded))
			if candidate == "http" || candidate == "https" {
				return candidate
			}
		}
	}
	if r.TLS != nil {
		return "https"
	}
	return "http"
}

func (h *Handler) isTrustedProxy(r *http.Request) bool {
	if len(h.trustedProxies) == 0 {
		return false
	}
	remoteIP := remoteIPFromAddr(r.RemoteAddr)
	if remoteIP == nil {
		return false
	}
	for _, network := range h.trustedProxies {
		if network.Contains(remoteIP) {
			return true
		}
	}
	return false
}

func remoteIPFromAddr(remoteAddr string) net.IP {
	host, _, err := net.SplitHostPort(strings.TrimSpace(remoteAddr))
	if err == nil && host != "" {
		return net.ParseIP(host)
	}
	return net.ParseIP(strings.TrimSpace(remoteAddr))
}

func parseTrustedProxyCIDRs(items []string) ([]*net.IPNet, error) {
	if len(items) == 0 {
		return nil, nil
	}
	trusted := make([]*net.IPNet, 0, len(items))
	for _, item := range items {
		candidate := strings.TrimSpace(item)
		if candidate == "" {
			continue
		}
		if ip := net.ParseIP(candidate); ip != nil {
			bits := 32
			if ip.To4() == nil {
				bits = 128
			}
			trusted = append(trusted, &net.IPNet{
				IP:   ip,
				Mask: net.CIDRMask(bits, bits),
			})
			continue
		}
		_, network, err := net.ParseCIDR(candidate)
		if err != nil {
			return nil, fmt.Errorf("%q: %w", candidate, err)
		}
		trusted = append(trusted, network)
	}
	return trusted, nil
}

func buildCoreHTTPClient(cfg Config, coreTLS bool) (*http.Client, error) {
	caFile := strings.TrimSpace(cfg.CoreCAFile)
	clientCertFile := strings.TrimSpace(cfg.CoreClientCertFile)
	clientKeyFile := strings.TrimSpace(cfg.CoreClientKeyFile)
	serverName := strings.TrimSpace(cfg.CoreTLSServerName)

	if (clientCertFile == "") != (clientKeyFile == "") {
		return nil, fmt.Errorf("both core client cert and key files must be provided together")
	}
	useCustomTLS := coreTLS || caFile != "" || clientCertFile != "" || serverName != "" || cfg.CoreTLSInsecureSkipVerify
	if !useCustomTLS {
		return &http.Client{Timeout: cfg.Timeout}, nil
	}

	tlsConfig := &tls.Config{
		MinVersion:         tls.VersionTLS12,
		InsecureSkipVerify: cfg.CoreTLSInsecureSkipVerify,
	}
	if serverName != "" {
		tlsConfig.ServerName = serverName
	}
	if caFile != "" {
		pemBytes, err := os.ReadFile(caFile)
		if err != nil {
			return nil, fmt.Errorf("failed to read core CA file: %w", err)
		}
		roots, err := x509.SystemCertPool()
		if err != nil || roots == nil {
			roots = x509.NewCertPool()
		}
		if ok := roots.AppendCertsFromPEM(pemBytes); !ok {
			return nil, fmt.Errorf("failed to parse core CA file")
		}
		tlsConfig.RootCAs = roots
	}
	if clientCertFile != "" && clientKeyFile != "" {
		clientCert, err := tls.LoadX509KeyPair(clientCertFile, clientKeyFile)
		if err != nil {
			return nil, fmt.Errorf("failed to load core client certificate: %w", err)
		}
		tlsConfig.Certificates = []tls.Certificate{clientCert}
	}

	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   30 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          100,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		TLSClientConfig:       tlsConfig,
	}
	return &http.Client{
		Timeout:   cfg.Timeout,
		Transport: transport,
	}, nil
}

func (h *Handler) clientRateKey(r *http.Request) string {
	if h.isTrustedProxy(r) {
		forwarded := strings.TrimSpace(r.Header.Get("X-Forwarded-For"))
		if forwarded != "" {
			if idx := strings.Index(forwarded, ","); idx >= 0 {
				forwarded = forwarded[:idx]
			}
			forwarded = strings.TrimSpace(forwarded)
			if forwarded != "" {
				return forwarded
			}
		}
	}
	host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr))
	if err == nil && host != "" {
		return host
	}
	if strings.TrimSpace(r.RemoteAddr) != "" {
		return strings.TrimSpace(r.RemoteAddr)
	}
	return ""
}

func canonicalOrigin(origin string) string {
	return strings.TrimRight(strings.ToLower(strings.TrimSpace(origin)), "/")
}

func (h *Handler) isRateLimited(r *http.Request, now time.Time) bool {
	if h.cfg.RateLimitRPS <= 0 {
		return false
	}
	key := h.clientRateKey(r)
	if key == "" {
		key = "unknown"
	}

	h.rateLimitMu.Lock()
	defer h.rateLimitMu.Unlock()

	for k, entry := range h.rateLimiters {
		if now.Sub(entry.lastSeen) > rateLimiterIdleTTL {
			delete(h.rateLimiters, k)
		}
	}

	entry, ok := h.rateLimiters[key]
	if !ok {
		entry = &clientLimiter{
			limiter: rate.NewLimiter(rate.Limit(h.cfg.RateLimitRPS), max(1, h.cfg.RateLimitBurst)),
		}
		h.rateLimiters[key] = entry
	}
	entry.lastSeen = now
	return !entry.limiter.Allow()
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
			"novaadapt_bridge_rate_limited_total %d\n"+
			"novaadapt_bridge_session_issued_total %d\n"+
			"novaadapt_bridge_session_revoked_total %d\n"+
			"novaadapt_bridge_ws_rejected_total %d\n"+
			"novaadapt_bridge_ws_active_connections %d\n"+
			"novaadapt_bridge_upstream_errors_total %d\n",
		atomic.LoadUint64(&h.requestsTotal),
		atomic.LoadUint64(&h.unauthorizedTotal),
		atomic.LoadUint64(&h.rateLimitedTotal),
		atomic.LoadUint64(&h.sessionIssuedTotal),
		atomic.LoadUint64(&h.sessionRevokedTotal),
		atomic.LoadUint64(&h.wsRejectedTotal),
		atomic.LoadInt64(&h.wsActiveConnections),
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
