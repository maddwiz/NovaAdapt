package relay

import (
	"encoding/base64"
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

func TestRequiredScopeForRetryFailedRoute(t *testing.T) {
	scope := requiredScopeForRoute(http.MethodPost, "/plans/plan-1/retry_failed")
	if scope != scopeApprove {
		t.Fatalf("expected %q scope, got %q", scopeApprove, scope)
	}

	scopeAsync := requiredScopeForRoute(http.MethodPost, "/plans/plan-1/retry_failed_async")
	if scopeAsync != scopeApprove {
		t.Fatalf("expected %q scope, got %q", scopeApprove, scopeAsync)
	}
}

func TestRequiredScopeForTerminalAndMemoryRoutes(t *testing.T) {
	if got := requiredScopeForRoute(http.MethodPost, "/terminal/sessions"); got != scopeRun {
		t.Fatalf("expected %q scope for terminal start, got %q", scopeRun, got)
	}
	if got := requiredScopeForRoute(http.MethodPost, "/terminal/sessions/abc/input"); got != scopeRun {
		t.Fatalf("expected %q scope for terminal input, got %q", scopeRun, got)
	}
	if got := requiredScopeForRoute(http.MethodPost, "/terminal/sessions/abc/close"); got != scopeRun {
		t.Fatalf("expected %q scope for terminal close, got %q", scopeRun, got)
	}
	if got := requiredScopeForRoute(http.MethodPost, "/memory/recall"); got != scopeRead {
		t.Fatalf("expected %q scope for memory recall, got %q", scopeRead, got)
	}
	if got := requiredScopeForRoute(http.MethodPost, "/memory/ingest"); got != scopeRun {
		t.Fatalf("expected %q scope for memory ingest, got %q", scopeRun, got)
	}
	if got := requiredScopeForRoute(http.MethodPost, "/browser/action"); got != scopeRun {
		t.Fatalf("expected %q scope for browser action, got %q", scopeRun, got)
	}
	if got := requiredScopeForRoute(http.MethodGet, "/browser/status"); got != scopeRead {
		t.Fatalf("expected %q scope for browser status, got %q", scopeRead, got)
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

func TestDeviceAllowlistAdminRoutes(t *testing.T) {
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

	rrList := httptest.NewRecorder()
	reqList := httptest.NewRequest(http.MethodGet, "/auth/devices", nil)
	reqList.Header.Set("Authorization", "Bearer bridge")
	reqList.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrList, reqList)
	if rrList.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/devices, got %d body=%s", rrList.Code, rrList.Body.String())
	}
	var listPayload map[string]any
	if err := json.Unmarshal(rrList.Body.Bytes(), &listPayload); err != nil {
		t.Fatalf("unmarshal device list payload: %v", err)
	}
	if count := toInt(listPayload["count"]); count != 1 {
		t.Fatalf("expected device count 1, got %#v", listPayload)
	}

	rrAdd := httptest.NewRecorder()
	reqAdd := httptest.NewRequest(http.MethodPost, "/auth/devices", strings.NewReader(`{"device_id":"halo-1"}`))
	reqAdd.Header.Set("Authorization", "Bearer bridge")
	reqAdd.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrAdd, reqAdd)
	if rrAdd.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/devices add, got %d body=%s", rrAdd.Code, rrAdd.Body.String())
	}
	var addPayload map[string]any
	if err := json.Unmarshal(rrAdd.Body.Bytes(), &addPayload); err != nil {
		t.Fatalf("unmarshal add payload: %v", err)
	}
	if added, ok := addPayload["added"].(bool); !ok || !added {
		t.Fatalf("expected added=true payload, got %#v", addPayload)
	}
	if count := toInt(addPayload["count"]); count != 2 {
		t.Fatalf("expected count=2 after add, got %#v", addPayload)
	}

	rrIssue := httptest.NewRecorder()
	reqIssue := httptest.NewRequest(
		http.MethodPost,
		"/auth/session",
		strings.NewReader(`{"subject":"halo","scopes":["read"],"device_id":"halo-1","ttl_seconds":120}`),
	)
	reqIssue.Header.Set("Authorization", "Bearer bridge")
	reqIssue.Header.Set("X-Device-ID", "halo-1")
	h.ServeHTTP(rrIssue, reqIssue)
	if rrIssue.Code != http.StatusOK {
		t.Fatalf("expected 200 issuing token for added device, got %d body=%s", rrIssue.Code, rrIssue.Body.String())
	}

	rrRemove := httptest.NewRecorder()
	reqRemove := httptest.NewRequest(http.MethodPost, "/auth/devices/remove", strings.NewReader(`{"device_id":"halo-1"}`))
	reqRemove.Header.Set("Authorization", "Bearer bridge")
	reqRemove.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrRemove, reqRemove)
	if rrRemove.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/devices/remove, got %d body=%s", rrRemove.Code, rrRemove.Body.String())
	}
	var removePayload map[string]any
	if err := json.Unmarshal(rrRemove.Body.Bytes(), &removePayload); err != nil {
		t.Fatalf("unmarshal remove payload: %v", err)
	}
	if removed, ok := removePayload["removed"].(bool); !ok || !removed {
		t.Fatalf("expected removed=true payload, got %#v", removePayload)
	}

	rrIssueRemoved := httptest.NewRecorder()
	reqIssueRemoved := httptest.NewRequest(
		http.MethodPost,
		"/auth/session",
		strings.NewReader(`{"subject":"halo","scopes":["read"],"device_id":"halo-1","ttl_seconds":120}`),
	)
	reqIssueRemoved.Header.Set("Authorization", "Bearer bridge")
	reqIssueRemoved.Header.Set("X-Device-ID", "iphone-1")
	h.ServeHTTP(rrIssueRemoved, reqIssueRemoved)
	if rrIssueRemoved.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 issuing token for removed device, got %d body=%s", rrIssueRemoved.Code, rrIssueRemoved.Body.String())
	}
	if !strings.Contains(rrIssueRemoved.Body.String(), "device_id is not in allowed list") {
		t.Fatalf("expected removed-device validation error, got %s", rrIssueRemoved.Body.String())
	}
}

func TestDeviceAllowlistRoutesRequireAdminScope(t *testing.T) {
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

	rrList := httptest.NewRecorder()
	reqList := httptest.NewRequest(http.MethodGet, "/auth/devices", nil)
	reqList.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rrList, reqList)
	if rrList.Code != http.StatusForbidden {
		t.Fatalf("expected 403 on /auth/devices for non-admin token, got %d body=%s", rrList.Code, rrList.Body.String())
	}

	rrAdd := httptest.NewRecorder()
	reqAdd := httptest.NewRequest(http.MethodPost, "/auth/devices", strings.NewReader(`{"device_id":"iphone-1"}`))
	reqAdd.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rrAdd, reqAdd)
	if rrAdd.Code != http.StatusForbidden {
		t.Fatalf("expected 403 on /auth/devices add for non-admin token, got %d body=%s", rrAdd.Code, rrAdd.Body.String())
	}

	rrRemove := httptest.NewRecorder()
	reqRemove := httptest.NewRequest(http.MethodPost, "/auth/devices/remove", strings.NewReader(`{"device_id":"iphone-1"}`))
	reqRemove.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rrRemove, reqRemove)
	if rrRemove.Code != http.StatusForbidden {
		t.Fatalf("expected 403 on /auth/devices/remove for non-admin token, got %d body=%s", rrRemove.Code, rrRemove.Body.String())
	}
}

func TestPairingRouteIssuesManifestAndDeepLink(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
		BridgeToken: "bridge",
		Timeout:     5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(
		http.MethodPost,
		"/auth/pair",
		strings.NewReader(`{"subject":"android-user","device_id":"android-operator-1","ttl_seconds":86400,"auto_connect":true}`),
	)
	req.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/pair, got %d body=%s", rr.Code, rr.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal pairing payload: %v", err)
	}
	if status := strings.TrimSpace(toString(payload["status"])); status != "ok" {
		t.Fatalf("expected status ok, got %#v", payload)
	}
	if got := strings.TrimSpace(toString(payload["subject"])); got != "android-user" {
		t.Fatalf("expected subject android-user, got %#v", payload)
	}
	if got := strings.TrimSpace(toString(payload["device_id"])); got != "android-operator-1" {
		t.Fatalf("expected device_id android-operator-1, got %#v", payload)
	}
	pairingCode := strings.TrimSpace(toString(payload["pairing_code"]))
	pairingURI := strings.TrimSpace(toString(payload["pairing_uri"]))
	if pairingCode == "" || pairingURI == "" {
		t.Fatalf("expected pairing code and uri, got %#v", payload)
	}
	if !strings.Contains(pairingURI, "novaadapt://pair?payload=") {
		t.Fatalf("expected pairing uri, got %q", pairingURI)
	}

	rawManifest, ok := payload["manifest"].(map[string]any)
	if !ok {
		t.Fatalf("expected manifest object, got %#v", payload["manifest"])
	}
	if got := strings.TrimSpace(toString(rawManifest["bridge_http_url"])); got != "http://example.com" {
		t.Fatalf("expected bridge_http_url http://example.com, got %#v", rawManifest)
	}
	if got := strings.TrimSpace(toString(rawManifest["ws_url"])); got != "ws://example.com/ws" {
		t.Fatalf("expected ws_url ws://example.com/ws, got %#v", rawManifest)
	}
	if strings.TrimSpace(toString(rawManifest["token"])) == "" {
		t.Fatalf("expected operator token in manifest, got %#v", rawManifest)
	}
	if strings.TrimSpace(toString(rawManifest["admin_token"])) == "" {
		t.Fatalf("expected admin token in manifest, got %#v", rawManifest)
	}

	decoded, err := base64.RawURLEncoding.DecodeString(pairingCode)
	if err != nil {
		t.Fatalf("decode pairing code: %v", err)
	}
	var decodedManifest map[string]any
	if err := json.Unmarshal(decoded, &decodedManifest); err != nil {
		t.Fatalf("unmarshal decoded pairing code: %v", err)
	}
	if got := strings.TrimSpace(toString(decodedManifest["device_id"])); got != "android-operator-1" {
		t.Fatalf("expected decoded device_id android-operator-1, got %#v", decodedManifest)
	}
}

func TestPairingRouteAutoAddsAllowedDevice(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL:      "http://example.com",
		BridgeToken:      "bridge",
		AllowedDeviceIDs: []string{"desktop-admin"},
		Timeout:          5 * time.Second,
	})
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(
		http.MethodPost,
		"/auth/pair",
		strings.NewReader(`{"subject":"android-user","device_id":"android-operator-2","include_admin_token":false,"auto_allowlist":true}`),
	)
	req.Header.Set("Authorization", "Bearer bridge")
	req.Header.Set("X-Device-ID", "desktop-admin")
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200 from /auth/pair, got %d body=%s", rr.Code, rr.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal pairing payload: %v", err)
	}
	if added, ok := payload["added_to_allowlist"].(bool); !ok || !added {
		t.Fatalf("expected added_to_allowlist=true, got %#v", payload)
	}
	if !h.isAllowedDevice("android-operator-2") {
		t.Fatalf("expected new device to be allowlisted")
	}
	rawManifest, ok := payload["manifest"].(map[string]any)
	if !ok {
		t.Fatalf("expected manifest object, got %#v", payload["manifest"])
	}
	if _, hasAdminToken := rawManifest["admin_token"]; hasAdminToken {
		t.Fatalf("expected admin token to be omitted when include_admin_token=false, got %#v", rawManifest)
	}
}

func TestPairingRouteRequiresAdminScope(t *testing.T) {
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
	req := httptest.NewRequest(http.MethodPost, "/auth/pair", strings.NewReader(`{"subject":"android"}`))
	req.Header.Set("Authorization", "Bearer "+readToken)
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-admin token on /auth/pair, got %d body=%s", rr.Code, rr.Body.String())
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

func TestSessionTokenRevocationBySessionID(t *testing.T) {
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
	sessionID := strings.TrimSpace(toString(issuePayload["session_id"]))
	if sessionToken == "" || sessionID == "" {
		t.Fatalf("expected session token and session_id")
	}

	rrRevoke := httptest.NewRecorder()
	reqRevoke := httptest.NewRequest(http.MethodPost, "/auth/session/revoke", strings.NewReader(`{"session_id":"`+sessionID+`"}`))
	reqRevoke.Header.Set("Authorization", "Bearer bridge")
	h.ServeHTTP(rrRevoke, reqRevoke)
	if rrRevoke.Code != http.StatusOK {
		t.Fatalf("revoke by session_id failed: %d body=%s", rrRevoke.Code, rrRevoke.Body.String())
	}

	rrModels := httptest.NewRecorder()
	reqModels := httptest.NewRequest(http.MethodGet, "/models", nil)
	reqModels.Header.Set("Authorization", "Bearer "+sessionToken)
	h.ServeHTTP(rrModels, reqModels)
	if rrModels.Code != http.StatusUnauthorized {
		t.Fatalf("expected session revoked by id to be unauthorized, got %d body=%s", rrModels.Code, rrModels.Body.String())
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

func TestSessionIssueAndRevokeMetricsIncrement(t *testing.T) {
	h, err := NewHandler(Config{
		CoreBaseURL: "http://example.com",
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

	rrMetrics := httptest.NewRecorder()
	reqMetrics := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	h.ServeHTTP(rrMetrics, reqMetrics)
	if rrMetrics.Code != http.StatusOK {
		t.Fatalf("metrics request failed: %d body=%s", rrMetrics.Code, rrMetrics.Body.String())
	}
	metrics := rrMetrics.Body.String()
	if !strings.Contains(metrics, "novaadapt_bridge_session_issued_total 1") {
		t.Fatalf("expected session issued metric count, got: %s", metrics)
	}
	if !strings.Contains(metrics, "novaadapt_bridge_session_revoked_total 1") {
		t.Fatalf("expected session revoked metric count, got: %s", metrics)
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
