package relay

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

const (
	defaultWSPollTimeoutSeconds  = 20.0
	defaultWSPollIntervalSeconds = 0.25
)

var wsUpgrader = websocket.Upgrader{
	CheckOrigin: func(_ *http.Request) bool {
		// Authorization is enforced at the bridge; allow non-browser and mobile origins.
		return true
	},
}

type wsClientMessage struct {
	Type           string         `json:"type"`
	ID             string         `json:"id,omitempty"`
	Method         string         `json:"method,omitempty"`
	Path           string         `json:"path,omitempty"`
	Query          string         `json:"query,omitempty"`
	Body           map[string]any `json:"body,omitempty"`
	IdempotencyKey string         `json:"idempotency_key,omitempty"`
	SinceID        *int64         `json:"since_id,omitempty"`
	SessionID      string         `json:"session_id,omitempty"`
	SinceSeq       *int64         `json:"since_seq,omitempty"`
	Limit          *int           `json:"limit,omitempty"`
	Input          string         `json:"input,omitempty"`
}

type wsSSEEvent struct {
	Event string
	Data  map[string]any
}

type wsJSONWriter struct {
	conn *websocket.Conn
	mu   sync.Mutex
}

func (w *wsJSONWriter) write(payload map[string]any) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	_ = w.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	return w.conn.WriteJSON(payload)
}

func (h *Handler) handleWebSocket(w http.ResponseWriter, r *http.Request, requestID string, auth authContext) int {
	if r.Method != http.MethodGet {
		h.writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "Method not allowed", "request_id": requestID})
		return http.StatusMethodNotAllowed
	}
	if !auth.hasScope(scopeRead) {
		h.writeJSON(w, http.StatusForbidden, map[string]any{"error": "Forbidden", "request_id": requestID})
		return http.StatusForbidden
	}
	if !h.tryAcquireWSConnection() {
		atomic.AddUint64(&h.wsRejectedTotal, 1)
		h.writeJSON(
			w,
			http.StatusTooManyRequests,
			map[string]any{"error": "Too many websocket connections", "request_id": requestID},
		)
		return http.StatusTooManyRequests
	}
	defer h.releaseWSConnection()

	conn, err := wsUpgrader.Upgrade(w, r, nil)
	if err != nil {
		return http.StatusBadRequest
	}
	writer := &wsJSONWriter{conn: conn}

	if err := writer.write(
		map[string]any{
			"type":       "hello",
			"request_id": requestID,
			"service":    "novaadapt-bridge-go",
		},
	); err != nil {
		_ = conn.Close()
		return http.StatusSwitchingProtocols
	}

	var lastEventID int64 = max64(0, parseInt64OrDefault(r.URL.Query().Get("since_id"), 0))
	pollTimeoutSeconds := clampFloat(
		parseFloatOrDefault(r.URL.Query().Get("poll_timeout"), defaultWSPollTimeoutSeconds),
		1.0,
		120.0,
	)
	pollIntervalSeconds := clampFloat(
		parseFloatOrDefault(r.URL.Query().Get("poll_interval"), defaultWSPollIntervalSeconds),
		0.05,
		5.0,
	)

	done := make(chan struct{})
	pumpDone := make(chan struct{})
	go func() {
		defer close(pumpDone)
		h.wsAuditPump(done, writer, requestID, &lastEventID, pollTimeoutSeconds, pollIntervalSeconds)
	}()

	for {
		var msg wsClientMessage
		if err := conn.ReadJSON(&msg); err != nil {
			break
		}
		if err := h.handleWSClientMessage(writer, requestID, &lastEventID, msg, auth); err != nil {
			break
		}
	}

	close(done)
	_ = conn.Close()
	<-pumpDone
	return http.StatusSwitchingProtocols
}

func (h *Handler) tryAcquireWSConnection() bool {
	maxConnections := h.cfg.MaxWSConnections
	if maxConnections <= 0 {
		atomic.AddInt64(&h.wsActiveConnections, 1)
		return true
	}
	for {
		current := atomic.LoadInt64(&h.wsActiveConnections)
		if current >= int64(maxConnections) {
			return false
		}
		if atomic.CompareAndSwapInt64(&h.wsActiveConnections, current, current+1) {
			return true
		}
	}
}

func (h *Handler) releaseWSConnection() {
	next := atomic.AddInt64(&h.wsActiveConnections, -1)
	if next >= 0 {
		return
	}
	atomic.StoreInt64(&h.wsActiveConnections, 0)
}

func (h *Handler) wsAuditPump(
	done <-chan struct{},
	writer *wsJSONWriter,
	requestID string,
	lastEventID *int64,
	pollTimeoutSeconds float64,
	pollIntervalSeconds float64,
) {
	for {
		select {
		case <-done:
			return
		default:
		}

		currentSinceID := atomic.LoadInt64(lastEventID)
		events, nextSinceID, err := h.pollAuditEvents(
			requestID,
			currentSinceID,
			pollTimeoutSeconds,
			pollIntervalSeconds,
		)
		if err != nil {
			if writeErr := writer.write(
				map[string]any{
					"type":       "error",
					"source":     "events",
					"error":      err.Error(),
					"request_id": requestID,
				},
			); writeErr != nil {
				return
			}
			select {
			case <-done:
				return
			case <-time.After(500 * time.Millisecond):
			}
			continue
		}

		if nextSinceID > currentSinceID {
			atomic.StoreInt64(lastEventID, nextSinceID)
		}

		for _, item := range events {
			if err := writer.write(
				map[string]any{
					"type":       "event",
					"event":      item.Event,
					"data":       item.Data,
					"request_id": requestID,
				},
			); err != nil {
				return
			}
		}

		if len(events) == 0 {
			select {
			case <-done:
				return
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
}

func (h *Handler) handleWSClientMessage(
	writer *wsJSONWriter,
	requestID string,
	lastEventID *int64,
	msg wsClientMessage,
	auth authContext,
) error {
	msgType := strings.ToLower(strings.TrimSpace(msg.Type))
	switch msgType {
	case "ping":
		return writer.write(map[string]any{"type": "pong", "id": msg.ID, "request_id": requestID})
	case "set_since_id":
		if msg.SinceID == nil {
			return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": "'since_id' is required", "request_id": requestID})
		}
		next := max64(0, *msg.SinceID)
		atomic.StoreInt64(lastEventID, next)
		return writer.write(map[string]any{"type": "ack", "id": msg.ID, "request_id": requestID, "since_id": next})
	case "terminal_list":
		return h.handleWSTerminalList(writer, requestID, msg, auth)
	case "terminal_start":
		return h.handleWSTerminalStart(writer, requestID, msg, auth)
	case "terminal_poll":
		return h.handleWSTerminalPoll(writer, requestID, msg, auth)
	case "terminal_input":
		return h.handleWSTerminalInput(writer, requestID, msg, auth)
	case "terminal_close":
		return h.handleWSTerminalClose(writer, requestID, msg, auth)
	case "browser_status":
		return h.handleWSBrowserGet(writer, requestID, msg, auth, "/browser/status", "browser_status")
	case "browser_pages":
		return h.handleWSBrowserGet(writer, requestID, msg, auth, "/browser/pages", "browser_pages")
	case "browser_action":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/action", "browser_action_result")
	case "browser_navigate":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/navigate", "browser_navigate_result")
	case "browser_click":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/click", "browser_click_result")
	case "browser_fill":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/fill", "browser_fill_result")
	case "browser_extract_text":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/extract_text", "browser_extract_text_result")
	case "browser_screenshot":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/screenshot", "browser_screenshot_result")
	case "browser_wait_for_selector":
		return h.handleWSBrowserPost(
			writer,
			requestID,
			msg,
			auth,
			"/browser/wait_for_selector",
			"browser_wait_for_selector_result",
		)
	case "browser_evaluate_js":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/evaluate_js", "browser_evaluate_js_result")
	case "browser_close":
		return h.handleWSBrowserPost(writer, requestID, msg, auth, "/browser/close", "browser_closed")
	case "command":
		return h.handleWSCommand(writer, requestID, msg, auth)
	default:
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      fmt.Sprintf("unsupported message type: %s", msg.Type),
				"request_id": requestID,
			},
		)
	}
}

func (h *Handler) handleWSTerminalList(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
) error {
	path := "/terminal/sessions"
	if !auth.canAccess(http.MethodGet, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodGet,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodGet,
		path,
		"",
		commandRequestID,
		"",
		nil,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            "terminal_sessions",
			"id":              msg.ID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSTerminalStart(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
) error {
	path := "/terminal/sessions"
	if !auth.canAccess(http.MethodPost, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodPost,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodPost,
		path,
		"",
		commandRequestID,
		strings.TrimSpace(msg.IdempotencyKey),
		msg.Body,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            "terminal_started",
			"id":              msg.ID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"idempotency_key": coreResult.IdempotencyKey,
			"replayed":        coreResult.ReplayDetected,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSTerminalPoll(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
) error {
	sessionID, err := normalizeTerminalSessionID(msg.SessionID)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}
	path := "/terminal/sessions/" + url.PathEscape(sessionID) + "/output"
	if !auth.canAccess(http.MethodGet, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodGet,
				"request_id": requestID,
			},
		)
	}

	sinceSeq := int64(0)
	if msg.SinceSeq != nil {
		sinceSeq = max64(0, *msg.SinceSeq)
	}
	limit := 600
	if msg.Limit != nil {
		limit = max(1, min(*msg.Limit, 5000))
	}
	query := fmt.Sprintf("since_seq=%d&limit=%d", sinceSeq, limit)

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodGet,
		path,
		query,
		commandRequestID,
		"",
		nil,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            "terminal_output",
			"id":              msg.ID,
			"session_id":      sessionID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSTerminalInput(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
) error {
	sessionID, err := normalizeTerminalSessionID(msg.SessionID)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	input := msg.Input
	if strings.TrimSpace(input) == "" && msg.Body != nil {
		rawInput := msg.Body["input"]
		if rawInput != nil {
			input = fmt.Sprintf("%v", rawInput)
		}
	}
	if input == "" {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": "'input' is required", "request_id": requestID})
	}

	path := "/terminal/sessions/" + url.PathEscape(sessionID) + "/input"
	if !auth.canAccess(http.MethodPost, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodPost,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodPost,
		path,
		"",
		commandRequestID,
		"",
		map[string]any{"input": input},
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            "terminal_input_result",
			"id":              msg.ID,
			"session_id":      sessionID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSTerminalClose(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
) error {
	sessionID, err := normalizeTerminalSessionID(msg.SessionID)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}
	path := "/terminal/sessions/" + url.PathEscape(sessionID) + "/close"
	if !auth.canAccess(http.MethodPost, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodPost,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodPost,
		path,
		"",
		commandRequestID,
		"",
		msg.Body,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            "terminal_closed",
			"id":              msg.ID,
			"session_id":      sessionID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSBrowserGet(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
	path string,
	responseType string,
) error {
	if !auth.canAccess(http.MethodGet, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodGet,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodGet,
		path,
		"",
		commandRequestID,
		"",
		nil,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            responseType,
			"id":              msg.ID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"path":            path,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSBrowserPost(
	writer *wsJSONWriter,
	requestID string,
	msg wsClientMessage,
	auth authContext,
	path string,
	responseType string,
) error {
	if !auth.canAccess(http.MethodPost, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     http.MethodPost,
				"request_id": requestID,
			},
		)
	}

	body := msg.Body
	if body == nil {
		body = map[string]any{}
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		http.MethodPost,
		path,
		"",
		commandRequestID,
		strings.TrimSpace(msg.IdempotencyKey),
		body,
	)
	if err != nil {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": err.Error(), "request_id": requestID})
	}

	return writer.write(
		map[string]any{
			"type":            responseType,
			"id":              msg.ID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"path":            path,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"idempotency_key": coreResult.IdempotencyKey,
			"replayed":        coreResult.ReplayDetected,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) handleWSCommand(writer *wsJSONWriter, requestID string, msg wsClientMessage, auth authContext) error {
	method := strings.ToUpper(strings.TrimSpace(msg.Method))
	if method == "" {
		if msg.Body != nil {
			method = http.MethodPost
		} else {
			method = http.MethodGet
		}
	}
	if method != http.MethodGet && method != http.MethodPost {
		return writer.write(map[string]any{"type": "error", "id": msg.ID, "error": "method must be GET or POST", "request_id": requestID})
	}

	path := normalizeWSPath(msg.Path)
	query := strings.TrimSpace(msg.Query)
	if idx := strings.Index(path, "?"); idx >= 0 {
		if query == "" {
			query = path[idx+1:]
		}
		path = path[:idx]
	}
	if !isForwardedPath(path) || isRawForwardPath(path) || path == "/ws" {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "path is not command-forwardable",
				"path":       path,
				"request_id": requestID,
			},
		)
	}
	if !auth.canAccess(method, path) {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      "forbidden by token scope",
				"path":       path,
				"method":     method,
				"request_id": requestID,
			},
		)
	}

	commandRequestID := normalizeRequestID("")
	coreResult, err := h.coreJSONRequest(
		method,
		path,
		query,
		commandRequestID,
		strings.TrimSpace(msg.IdempotencyKey),
		msg.Body,
	)
	if err != nil {
		return writer.write(
			map[string]any{
				"type":       "error",
				"id":         msg.ID,
				"error":      err.Error(),
				"request_id": requestID,
			},
		)
	}
	return writer.write(
		map[string]any{
			"type":            "command_result",
			"id":              msg.ID,
			"status":          coreResult.StatusCode,
			"payload":         coreResult.Payload,
			"core_request":    commandRequestID,
			"core_request_id": coreResult.CoreRequestID,
			"idempotency_key": coreResult.IdempotencyKey,
			"replayed":        coreResult.ReplayDetected,
			"request_id":      requestID,
		},
	)
}

func (h *Handler) pollAuditEvents(
	requestID string,
	sinceID int64,
	timeoutSeconds float64,
	intervalSeconds float64,
) ([]wsSSEEvent, int64, error) {
	query := fmt.Sprintf(
		"timeout=%s&interval=%s&since_id=%d",
		formatFloat(timeoutSeconds),
		formatFloat(intervalSeconds),
		max64(0, sinceID),
	)
	status, _, raw, err := h.coreRawRequest("/events/stream", query, requestID)
	if err != nil {
		return nil, sinceID, err
	}
	if status != http.StatusOK {
		return nil, sinceID, fmt.Errorf("events stream failed with status %d: %s", status, string(raw))
	}

	parsed := parseSSE(raw)
	out := make([]wsSSEEvent, 0, len(parsed))
	nextSinceID := sinceID
	for _, item := range parsed {
		if item.Event != "audit" {
			continue
		}
		out = append(out, item)
		if value, ok := asInt64(item.Data["id"]); ok && value > nextSinceID {
			nextSinceID = value
		}
	}
	return out, nextSinceID, nil
}

type coreJSONResult struct {
	StatusCode     int
	Payload        any
	CoreRequestID  string
	IdempotencyKey string
	ReplayDetected bool
}

func (h *Handler) coreJSONRequest(
	method string,
	corePath string,
	rawQuery string,
	requestID string,
	idempotencyKey string,
	body map[string]any,
) (coreJSONResult, error) {
	target, err := joinURL(h.cfg.CoreBaseURL, corePath, rawQuery)
	if err != nil {
		return coreJSONResult{StatusCode: http.StatusBadGateway}, fmt.Errorf("failed to build core URL: %w", err)
	}

	var reqBody io.Reader
	if method == http.MethodPost {
		if body == nil {
			body = map[string]any{}
		}
		encoded, err := json.Marshal(body)
		if err != nil {
			return coreJSONResult{StatusCode: http.StatusBadRequest}, fmt.Errorf("failed to encode command body: %w", err)
		}
		reqBody = bytes.NewReader(encoded)
	}

	req, err := http.NewRequest(method, target, reqBody)
	if err != nil {
		return coreJSONResult{StatusCode: http.StatusBadGateway}, fmt.Errorf("failed to create core request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", requestID)
	if strings.TrimSpace(idempotencyKey) != "" {
		req.Header.Set("Idempotency-Key", strings.TrimSpace(idempotencyKey))
	}
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return coreJSONResult{StatusCode: http.StatusBadGateway}, fmt.Errorf("core API unreachable: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return coreJSONResult{StatusCode: http.StatusBadGateway}, fmt.Errorf("failed to read core response: %w", err)
	}

	payload, ok := decodeAnyJSON(raw)
	if !ok {
		payload = map[string]any{"raw": string(raw), "request_id": requestID}
	} else {
		payload = attachRequestID(payload, requestID)
	}
	result := coreJSONResult{
		StatusCode:     resp.StatusCode,
		Payload:        payload,
		CoreRequestID:  strings.TrimSpace(resp.Header.Get("X-Request-ID")),
		IdempotencyKey: strings.TrimSpace(resp.Header.Get("Idempotency-Key")),
		ReplayDetected: strings.EqualFold(strings.TrimSpace(resp.Header.Get("X-Idempotency-Replayed")), "true"),
	}
	return result, nil
}

func (h *Handler) coreRawRequest(
	corePath string,
	rawQuery string,
	requestID string,
) (int, string, []byte, error) {
	target, err := joinURL(h.cfg.CoreBaseURL, corePath, rawQuery)
	if err != nil {
		return http.StatusBadGateway, "application/json", nil, fmt.Errorf("failed to build core URL: %w", err)
	}
	req, err := http.NewRequest(http.MethodGet, target, nil)
	if err != nil {
		return http.StatusBadGateway, "application/json", nil, fmt.Errorf("failed to create core request: %w", err)
	}
	req.Header.Set("X-Request-ID", requestID)
	if strings.TrimSpace(h.cfg.CoreToken) != "" {
		req.Header.Set("Authorization", "Bearer "+h.cfg.CoreToken)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return http.StatusBadGateway, "application/json", nil, fmt.Errorf("core API unreachable: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return http.StatusBadGateway, "application/json", nil, fmt.Errorf("failed to read core response: %w", err)
	}
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "text/plain; charset=utf-8"
	}
	return resp.StatusCode, contentType, body, nil
}

func parseSSE(raw []byte) []wsSSEEvent {
	lines := strings.Split(string(raw), "\n")
	currentEvent := "message"
	events := make([]wsSSEEvent, 0)
	for _, line := range lines {
		line = strings.TrimRight(line, "\r")
		if strings.HasPrefix(line, "event:") {
			value := strings.TrimSpace(strings.TrimPrefix(line, "event:"))
			if value != "" {
				currentEvent = value
			} else {
				currentEvent = "message"
			}
			continue
		}
		if strings.HasPrefix(line, "data:") {
			rawData := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			events = append(
				events,
				wsSSEEvent{
					Event: currentEvent,
					Data:  parseSSEData(rawData),
				},
			)
			currentEvent = "message"
		}
	}
	return events
}

func parseSSEData(raw string) map[string]any {
	var parsed any
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		return map[string]any{"raw": raw}
	}
	if obj, ok := parsed.(map[string]any); ok {
		return obj
	}
	return map[string]any{"value": parsed}
}

func normalizeWSPath(path string) string {
	value := strings.TrimSpace(path)
	if value == "" {
		return ""
	}
	if strings.Contains(value, "://") {
		return ""
	}
	if !strings.HasPrefix(value, "/") {
		value = "/" + value
	}
	return value
}

func normalizeTerminalSessionID(value string) (string, error) {
	sessionID := strings.TrimSpace(value)
	if sessionID == "" {
		return "", fmt.Errorf("'session_id' is required")
	}
	if strings.Contains(sessionID, "/") || strings.Contains(sessionID, "?") {
		return "", fmt.Errorf("invalid 'session_id'")
	}
	return sessionID, nil
}

func parseInt64OrDefault(value string, fallback int64) int64 {
	parsed, err := strconv.ParseInt(strings.TrimSpace(value), 10, 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func parseFloatOrDefault(value string, fallback float64) float64 {
	parsed, err := strconv.ParseFloat(strings.TrimSpace(value), 64)
	if err != nil {
		return fallback
	}
	return parsed
}

func clampFloat(value float64, min float64, max float64) float64 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func asInt64(value any) (int64, bool) {
	switch v := value.(type) {
	case int:
		return int64(v), true
	case int64:
		return v, true
	case float64:
		return int64(v), true
	case json.Number:
		parsed, err := v.Int64()
		return parsed, err == nil
	case string:
		parsed, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64)
		return parsed, err == nil
	default:
		return 0, false
	}
}

func max64(a int64, b int64) int64 {
	if a > b {
		return a
	}
	return b
}
