package relay

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"
)

var allowedPaths = map[string]struct{}{
	"/models":    {},
	"/history":   {},
	"/run":       {},
	"/run_async": {},
	"/undo":      {},
	"/check":     {},
	"/jobs":      {},
}

// Config controls bridge relay behavior.
type Config struct {
	CoreBaseURL string
	BridgeToken string
	CoreToken   string
	Timeout     time.Duration
}

// Handler is an HTTP handler that secures and forwards requests to NovaAdapt core.
type Handler struct {
	cfg    Config
	client *http.Client
}

// NewHandler creates a configured bridge relay handler.
func NewHandler(cfg Config) (*Handler, error) {
	if strings.TrimSpace(cfg.CoreBaseURL) == "" {
		return nil, fmt.Errorf("core base url is required")
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 30 * time.Second
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
	if r.URL.Path == "/health" {
		h.writeJSON(w, http.StatusOK, map[string]any{"ok": true, "service": "novaadapt-bridge-go"})
		return
	}

	if !h.authorized(r) {
		h.writeJSONWithStatus(w, http.StatusUnauthorized, map[string]any{"error": "Unauthorized"}, true)
		return
	}

	if !isForwardedPath(r.URL.Path) {
		h.writeJSON(w, http.StatusNotFound, map[string]any{"error": "Not found"})
		return
	}

	if r.Method != http.MethodGet && r.Method != http.MethodPost {
		h.writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "Method not allowed"})
		return
	}

	body, err := h.readBody(r)
	if err != nil {
		h.writeJSON(w, http.StatusBadRequest, map[string]any{"error": err.Error()})
		return
	}

	status, payload := h.forward(r, body)
	h.writeJSON(w, status, payload)
}

func isForwardedPath(p string) bool {
	if strings.HasPrefix(p, "/jobs/") {
		id := strings.TrimSpace(strings.TrimPrefix(p, "/jobs/"))
		return id != ""
	}
	_, ok := allowedPaths[p]
	return ok
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
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read request body")
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

func (h *Handler) forward(r *http.Request, body []byte) (int, map[string]any) {
	target, err := joinURL(h.cfg.CoreBaseURL, r.URL.Path, r.URL.RawQuery)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to build core URL"}
	}

	var reqBody io.Reader
	if r.Method == http.MethodPost {
		reqBody = bytes.NewReader(body)
	}

	req, err := http.NewRequest(r.Method, target, reqBody)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to create core request"}
	}
	req.Header.Set("Content-Type", "application/json")
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": fmt.Sprintf("Core API unreachable: %v", err)}
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return http.StatusBadGateway, map[string]any{"error": "Failed to read core response"}
	}

	var payload map[string]any
	if len(bytes.TrimSpace(raw)) == 0 {
		payload = map[string]any{}
	} else if err := json.Unmarshal(raw, &payload); err != nil {
		payload = map[string]any{"raw": string(raw)}
	}

	return resp.StatusCode, payload
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

func (h *Handler) writeJSON(w http.ResponseWriter, status int, payload map[string]any) {
	h.writeJSONWithStatus(w, status, payload, false)
}

func (h *Handler) writeJSONWithStatus(w http.ResponseWriter, status int, payload map[string]any, unauthorized bool) {
	encoded, _ := json.Marshal(payload)
	w.Header().Set("Content-Type", "application/json")
	if unauthorized {
		w.Header().Set("WWW-Authenticate", "Bearer")
	}
	w.WriteHeader(status)
	_, _ = w.Write(encoded)
}
