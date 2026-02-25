package relay

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestSessionTokenIssueAndScopeEnforcement(t *testing.T) {
	runCalls := 0
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/models":
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
		case "/run":
			runCalls++
			_, _ = w.Write([]byte(`{"status":"ok"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	defer core.Close()

	h, err := NewHandler(Config{
		CoreBaseURL: core.URL,
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rrIssue := httptest.NewRecorder()
	reqIssue := httptest.NewRequest(
		http.MethodPost,
		"/auth/session",
		strings.NewReader(`{"subject":"iphone","scopes":["read"],"ttl_seconds":120}`),
	)
	reqIssue.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrIssue, reqIssue)
	if rrIssue.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/session got %d body=%s", rrIssue.Code, rrIssue.Body.String())
	}
	var issuePayload map[string]any
	if err := json.Unmarshal(rrIssue.Body.Bytes(), &issuePayload); err != nil {
		t.Fatalf("unmarshal issue payload: %v", err)
	}
	sessionToken := strings.TrimSpace(toString(issuePayload["token"]))
	if sessionToken == "" {
		t.Fatalf("expected issued session token")
	}

	rrModels := httptest.NewRecorder()
	reqModels := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqModels.Header.Set("Authorization", "Bearer "+sessionToken)
	h.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusOK {
		t.Fatalf("expected 200 for read-scoped /models request, got %d body=%s", rrModels.Code, rrModels.Body.String())
	}

	rrRun := httptest.NewRecorder()
	reqRun := httptest.NewRequest(http.MethodPost, "/run", strings.NewReader(`{"objective":"test"}`))
	reqRun.Header.Set("Authorization", "Bearer "+sessionToken)
	h.ServeHTTP(rrRun, reqRun)
	if rrRun.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for read-scoped /run request, got %d body=%s", rrRun.Code, rrRun.Body.String())
	}
	if runCalls != 0 {
		t.Fatalf("expected no upstream /run call, got %d", runCalls)
	}
}

func TestSessionTokenCannotIssueSessionWithoutAdminScope(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	readToken, _, err := h.issueSessionToken("reader", []string{scopeRead}, "", 120)
	if err != nil {
		t.Fatalf("issue read token: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/auth/session", strings.NewReader(`{"scopes":["read"]}`))
	req.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-admin token on /auth/session, got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestSessionTokenDeviceBinding(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(Config{
		CoreBaseURL:      core.URL,
		BridgeToken:      "bridge",
		AllowedDeviceIDs: []string{"iphone-1"},
		Timeout:          5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rrIssue := httptest.NewRecorder()
	reqIssue := httptest.NewRequest(
		http.MethodPost,
		"/auth/session",
		strings.NewReader(`{"subject":"iphone","scopes":["read"],"device_id":"iphone-1","ttl_seconds":120}`),
	)
	reqIssue.Header.Set("Authorization", "Bearer bridge")
	reqIssue.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrIssue, reqIssue)
	if rrIssue.Code != http.StatusOK {
		t.Fatalf("expected 200 issuing device-bound token, got %d body=%s", rrIssue.Code, rrIssue.Body.String())
	}
	var issuePayload map[string]any
	if err := json.Unmarshal(rrIssue.Body.Bytes(), &issuePayload); err != nil {
		t.Fatalf("unmarshal issue payload: %v", err)
	}
	sessionToken := strings.TrimSpace(toString(issuePayload["token"]))
	if sessionToken == "" {
		t.Fatalf("expected issued session token")
	}

	rrWrongDevice := httptest.NewRecorder()
	reqWrongDevice := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqWrongDevice.Header.Set("Authorization", "Bearer "+sessionToken)
	reqWrongDevice.Header.Set("X-Device-ID", "halo-1")
	h.ServeHTTP(rrWrongDevice, reqWrongDevice)
	if rrWrongDevice.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for mismatched device, got %d body=%s", rrWrongDevice.Code, rrWrongDevice.Body.String())
	}

	rrBoundDevice := httptest.NewRecorder()
	reqBoundDevice := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqBoundDevice.Header.Set("Authorization", "Bearer "+sessionToken)
	reqBoundDevice.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrBoundDevice, reqBoundDevice)
	if rrBoundDevice.Code != http.StatusOK {
		t.Fatalf("expected 200 for matching device, got %d body=%s", rrBoundDevice.Code, rrBoundDevice.Body.String())
	}
}

func TestSessionTokenRejectsUnknownScopes(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/auth/session", strings.NewReader(`{"scopes":["read","wizard"]}`))
	req.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for unknown scope, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "unknown scope") {
		t.Fatalf("expected unknown scope error, got %s", rr.Body.String())
	}
}

func TestSessionTokenRevocationBlocksFurtherAccess(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	h, err := NewHandler(Config{
		CoreBaseURL: core.URL,
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rrIssue := httptest.NewRecorder()
	reqIssue := httptest.NewRequest(http.MethodPost, "/auth/session", strings.NewReader(`{"scopes":["read"]}`))
	reqIssue.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrIssue, reqIssue)
	if rrIssue.Code != http.StatusOK {
		t.Fatalf("issue session token failed: %d body=%s", rrIssue.Code, rrIssue.Body.String())
	}
	var issuePayload map[string]any
	if err := json.Unmarshal(rrIssue.Body.Bytes(), &issuePayload); err != nil {
		t.Fatalf("unmarshal issue payload: %v", err)
	}
	sessionToken := strings.TrimSpace(toString(issuePayload["token"]))
	if sessionToken == "" {
		t.Fatalf("expected issued session token")
	}

	rrRevoke := httptest.NewRecorder()
	reqRevoke := httptest.NewRequest(http.MethodPost, "/auth/session/revoke", strings.NewReader(`{"token":"`+sessionToken+`"}`))
	reqRevoke.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRevoke, reqRevoke)
	if rrRevoke.Code != http.StatusOK {
		t.Fatalf("revoke session token failed: %d body=%s", rrRevoke.Code, rrRevoke.Body.String())
	}

	rrModels := httptest.NewRecorder()
	reqModels := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqModels.Header.Set("Authorization", "Bearer "+sessionToken)
	h.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusUnauthorized {
		t.Fatalf("expected revoked token to be unauthorized, got %d body=%s", rrModels.Code, rrModels.Body.String())
	}
}

func TestSessionTokenRevocationRequiresAdminScope(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	adminToken, _, err := h.issueSessionToken("admin", []string{scopeAdmin}, "", 120)
	if err != nil {
		t.Fatalf("issue admin token: %v", err)
	}
	readToken, _, err := h.issueSessionToken("reader", []string{scopeRead}, "", 120)
	if err != nil {
		t.Fatalf("issue read token: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/auth/session/revoke", strings.NewReader(`{"token":"`+adminToken+`"}`))
	req.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-admin token on /auth/session/revoke, got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestSessionTokenRevocationRejectsInvalidToken(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/auth/session/revoke", strings.NewReader(`{"token":"not-a-session-token"}`))
	req.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid token, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "invalid session token") {
		t.Fatalf("expected invalid session token error, got %s", rr.Body.String())
	}
}

func TestSessionTokenRevocationPersistsAcrossHandlerRestart(t *testing.T) {
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			_, _ = w.Write([]byte(`[{"name":"local"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	defer core.Close()

	tempDir := t.TempDir()
	revocationStorePath := filepath.Join(tempDir, "revocations.json")

	h1, err := NewHandler(
		Config{
			CoreBaseURL:         core.URL,
			BridgeToken:         "bridge",
			RevocationStorePath: revocationStorePath,
			Timeout:             5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler #1: %v", err)
	}

	rrIssue := httptest.NewRecorder()
	reqIssue := httptest.NewRequest(http.MethodPost, "/auth/session", strings.NewReader(`{"scopes":["read"]}`))
	reqIssue.Header.Set("Authorization", "Bearer bridge")
	h1.ServeHTTP(rrIssue, reqIssue)
	if rrIssue.Code != http.StatusOK {
		t.Fatalf("issue session token failed: %d body=%s", rrIssue.Code, rrIssue.Body.String())
	}
	var issuePayload map[string]any
	if err := json.Unmarshal(rrIssue.Body.Bytes(), &issuePayload); err != nil {
		t.Fatalf("unmarshal issue payload: %v", err)
	}
	sessionToken := strings.TrimSpace(toString(issuePayload["token"]))
	if sessionToken == "" {
		t.Fatalf("expected issued session token")
	}

	rrRevoke := httptest.NewRecorder()
	reqRevoke := httptest.NewRequest(http.MethodPost, "/auth/session/revoke", strings.NewReader(`{"token":"`+sessionToken+`"}`))
	reqRevoke.Header.Set("Authorization", "Bearer bridge")
	h1.ServeHTTP(rrRevoke, reqRevoke)
	if rrRevoke.Code != http.StatusOK {
		t.Fatalf("revoke session token failed: %d body=%s", rrRevoke.Code, rrRevoke.Body.String())
	}
	if _, err := os.Stat(revocationStorePath); err != nil {
		t.Fatalf("expected revocation store file: %v", err)
	}

	h2, err := NewHandler(
		Config{
			CoreBaseURL:         core.URL,
			BridgeToken:         "bridge",
			RevocationStorePath: revocationStorePath,
			Timeout:             5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler #2: %v", err)
	}

	rrModels := httptest.NewRecorder()
	reqModels := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqModels.Header.Set("Authorization", "Bearer "+sessionToken)
	h2.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusUnauthorized {
		t.Fatalf("expected revoked token to remain unauthorized after restart, got %d body=%s", rrModels.Code, rrModels.Body.String())
	}
}

func TestInvalidRevocationStoreFailsHandlerInit(t *testing.T) {
	tempDir := t.TempDir()
	storePath := filepath.Join(tempDir, "revocations.json")
	if err := os.WriteFile(storePath, []byte("{not-json"), 0o600); err != nil {
		t.Fatalf("write invalid store: %v", err)
	}

	_, err := NewHandler(
		Config{
			CoreBaseURL:         "http://example.com",
			BridgeToken:         "bridge",
			RevocationStorePath: storePath,
			Timeout:             5 * time.Second,
		},
	)
	if err == nil {
		t.Fatalf("expected handler init to fail with invalid revocation store")
	}
}

func TestWebSocketReadScopedTokenCannotRunCommand(t *testing.T) {
	runCalls := 0
	core := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/events/stream":
			w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
			_, _ = w.Write([]byte("event: timeout\ndata: {\"request_id\":\"rid\"}\n\n"))
		case "/run":
			runCalls++
			_, _ = w.Write([]byte(`{"status":"ok"}`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	defer core.Close()

	h, err := NewHandler(Config{
		CoreBaseURL: core.URL,
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}
	token, _, err := h.issueSessionToken("reader", []string{scopeRead}, "", 120)
	if err != nil {
		t.Fatalf("issue session token: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?since_id=0&poll_timeout=1&poll_interval=0.1"
	headers := http.Header{}
	headers.Set("Authorization", "Bearer "+token)
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err != nil {
		t.Fatalf("dial websocket: %v", err)
	}
	defer conn.Close()

	hello := mustReadWSMessageByType(t, conn, "hello", 2*time.Second)
	if hello["type"] != "hello" {
		t.Fatalf("expected hello, got %#v", hello)
	}

	if err := conn.WriteJSON(
		map[string]any{
			"type":   "command",
			"id":     "cmd-run",
			"method": "POST",
			"path":   "/run",
			"body": map[string]any{
				"objective": "test",
			},
		},
	); err != nil {
		t.Fatalf("write command: %v", err)
	}

	msg := mustReadWSMessageByType(t, conn, "error", 2*time.Second)
	if msg["error"] != "forbidden by token scope" {
		t.Fatalf("expected forbidden scope error, got %#v", msg)
	}
	if runCalls != 0 {
		t.Fatalf("expected no upstream /run call, got %d", runCalls)
	}
}

func TestWebSocketRequiresReadScope(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}
	token, _, err := h.issueSessionToken("runner", []string{scopeRun}, "", 120)
	if err != nil {
		t.Fatalf("issue session token: %v", err)
	}

	server := httptest.NewServer(h)
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws"
	headers := http.Header{}
	headers.Set("Authorization", "Bearer "+token)
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		t.Fatalf("expected websocket authz error")
	}
	if resp == nil || resp.StatusCode != http.StatusForbidden {
		if resp == nil {
			t.Fatalf("expected forbidden response status")
		}
		t.Fatalf("expected 403 got %d", resp.StatusCode)
	}
}
