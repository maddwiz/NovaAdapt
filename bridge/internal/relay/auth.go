package relay

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	scopeAdmin   = "admin"
	scopeRead    = "read"
	scopeRun     = "run"
	scopePlan    = "plan"
	scopeApprove = "approve"
	scopeReject  = "reject"
	scopeUndo    = "undo"
	scopeCancel  = "cancel"
)

var allBridgeScopes = []string{
	scopeAdmin,
	scopeRead,
	scopeRun,
	scopePlan,
	scopeApprove,
	scopeReject,
	scopeUndo,
	scopeCancel,
}

var bridgeScopeSet = func() map[string]struct{} {
	out := make(map[string]struct{}, len(allBridgeScopes))
	for _, scope := range allBridgeScopes {
		out[scope] = struct{}{}
	}
	return out
}()

type authContext struct {
	Authorized bool
	TokenType  string
	Subject    string
	SessionID  string
	DeviceID   string
	Scopes     map[string]struct{}
	ExpiresAt  int64
}

func (ctx authContext) hasScope(scope string) bool {
	if !ctx.Authorized {
		return false
	}
	if _, ok := ctx.Scopes[scopeAdmin]; ok {
		return true
	}
	_, ok := ctx.Scopes[scope]
	return ok
}

func (ctx authContext) canAccess(method string, path string) bool {
	required := requiredScopeForRoute(method, path)
	if required == "" {
		return true
	}
	return ctx.hasScope(required)
}

type sessionTokenClaims struct {
	Sub      string   `json:"sub,omitempty"`
	Scopes   []string `json:"scopes,omitempty"`
	DeviceID string   `json:"device_id,omitempty"`
	JTI      string   `json:"jti,omitempty"`
	Exp      int64    `json:"exp"`
	Iat      int64    `json:"iat,omitempty"`
}

type revocationStorePayload struct {
	Version         int              `json:"version"`
	RevokedSessions map[string]int64 `json:"revoked_sessions"`
}

func (h *Handler) authenticate(r *http.Request) authContext {
	if strings.TrimSpace(h.cfg.BridgeToken) == "" && strings.TrimSpace(h.cfg.SessionSigningKey) == "" {
		return authContext{
			Authorized: true,
			TokenType:  "open",
			Subject:    "open-access",
			Scopes:     scopeSet(allBridgeScopes),
		}
	}

	token := extractRequestToken(r)
	if token == "" {
		return authContext{}
	}

	if strings.TrimSpace(h.cfg.BridgeToken) != "" &&
		subtle.ConstantTimeCompare([]byte(token), []byte(strings.TrimSpace(h.cfg.BridgeToken))) == 1 {
		deviceID, ok := h.resolveAndValidateDeviceID(r, "")
		if !ok {
			return authContext{}
		}
		return authContext{
			Authorized: true,
			TokenType:  "static",
			Subject:    "bridge-static-token",
			DeviceID:   deviceID,
			Scopes:     scopeSet(allBridgeScopes),
		}
	}

	claims, err := h.verifySessionToken(token)
	if err != nil {
		return authContext{}
	}
	if h.isSessionRevoked(claims.JTI, time.Now().Unix()) {
		return authContext{}
	}
	deviceID, ok := h.resolveAndValidateDeviceID(r, claims.DeviceID)
	if !ok {
		return authContext{}
	}
	subject := strings.TrimSpace(claims.Sub)
	if subject == "" {
		subject = "session"
	}
	return authContext{
		Authorized: true,
		TokenType:  "session",
		Subject:    subject,
		SessionID:  claims.JTI,
		DeviceID:   deviceID,
		Scopes:     scopeSet(claims.Scopes),
		ExpiresAt:  claims.Exp,
	}
}

func (h *Handler) issueSessionToken(
	subject string,
	scopes []string,
	deviceID string,
	ttlSeconds int,
) (string, sessionTokenClaims, error) {
	key := h.sessionSigningKey()
	if key == "" {
		return "", sessionTokenClaims{}, fmt.Errorf("session signing key is not configured")
	}
	normalizedScopes := normalizeScopes(scopes)
	if err := validateScopes(normalizedScopes); err != nil {
		return "", sessionTokenClaims{}, err
	}

	now := time.Now().Unix()
	ttl := ttlSeconds
	if ttl <= 0 {
		ttl = int(max(60, int(h.cfg.SessionTokenTTL.Seconds())))
	}
	if ttl > 24*3600 {
		ttl = 24 * 3600
	}
	sessionID, err := generateSessionID()
	if err != nil {
		return "", sessionTokenClaims{}, fmt.Errorf("failed to generate session id")
	}
	claims := sessionTokenClaims{
		Sub:      strings.TrimSpace(subject),
		Scopes:   normalizedScopes,
		DeviceID: strings.TrimSpace(deviceID),
		JTI:      sessionID,
		Iat:      now,
		Exp:      now + int64(ttl),
	}
	if claims.Sub == "" {
		claims.Sub = "bridge-session"
	}
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", sessionTokenClaims{}, err
	}
	body := base64.RawURLEncoding.EncodeToString(payload)
	signature := signSessionBody(body, key)
	token := "na1." + body + "." + signature
	return token, claims, nil
}

func (h *Handler) verifySessionToken(token string) (sessionTokenClaims, error) {
	key := h.sessionSigningKey()
	if key == "" {
		return sessionTokenClaims{}, fmt.Errorf("session signing key is not configured")
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 || parts[0] != "na1" {
		return sessionTokenClaims{}, fmt.Errorf("invalid token format")
	}
	body := parts[1]
	expectedSig := signSessionBody(body, key)
	if subtle.ConstantTimeCompare([]byte(parts[2]), []byte(expectedSig)) != 1 {
		return sessionTokenClaims{}, fmt.Errorf("invalid token signature")
	}

	raw, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return sessionTokenClaims{}, fmt.Errorf("invalid token payload")
	}
	var claims sessionTokenClaims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return sessionTokenClaims{}, fmt.Errorf("invalid token claims")
	}
	now := time.Now().Unix()
	if claims.Exp <= now {
		return sessionTokenClaims{}, fmt.Errorf("token expired")
	}
	claims.Scopes = normalizeScopes(claims.Scopes)
	if err := validateScopes(claims.Scopes); err != nil {
		return sessionTokenClaims{}, fmt.Errorf("invalid token scopes")
	}
	return claims, nil
}

func (h *Handler) sessionSigningKey() string {
	if strings.TrimSpace(h.cfg.SessionSigningKey) != "" {
		return strings.TrimSpace(h.cfg.SessionSigningKey)
	}
	return strings.TrimSpace(h.cfg.BridgeToken)
}

func (h *Handler) resolveAndValidateDeviceID(r *http.Request, tokenDeviceID string) (string, bool) {
	requestDeviceID := strings.TrimSpace(r.Header.Get("X-Device-ID"))
	if requestDeviceID == "" && r.URL.Path == "/ws" {
		requestDeviceID = strings.TrimSpace(r.URL.Query().Get("device_id"))
	}
	tokenDeviceID = strings.TrimSpace(tokenDeviceID)
	if requestDeviceID == "" {
		requestDeviceID = tokenDeviceID
	}
	if tokenDeviceID != "" && requestDeviceID != "" && tokenDeviceID != requestDeviceID {
		return "", false
	}

	if len(h.allowedDevices) == 0 {
		return requestDeviceID, true
	}
	if requestDeviceID == "" {
		return "", false
	}
	_, ok := h.allowedDevices[requestDeviceID]
	return requestDeviceID, ok
}

func requiredScopeForRoute(method string, path string) string {
	method = strings.ToUpper(strings.TrimSpace(method))
	if method == http.MethodGet {
		return scopeRead
	}
	if method != http.MethodPost {
		return ""
	}
	switch {
	case path == "/run" || path == "/run_async" || path == "/swarm/run" || path == "/check":
		return scopeRun
	case path == "/feedback" || path == "/memory/ingest":
		return scopeRun
	case path == "/memory/recall":
		return scopeRead
	case path == "/terminal/sessions" || (strings.HasPrefix(path, "/terminal/sessions/") && strings.HasSuffix(path, "/input")):
		return scopeRun
	case strings.HasPrefix(path, "/terminal/sessions/") && strings.HasSuffix(path, "/close"):
		return scopeRun
	case strings.HasPrefix(path, "/plugins/") && strings.HasSuffix(path, "/call"):
		return scopeRun
	case path == "/plans":
		return scopePlan
	case strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/approve"):
		return scopeApprove
	case strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/approve_async"):
		return scopeApprove
	case strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/retry_failed_async"):
		return scopeApprove
	case strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/retry_failed"):
		return scopeApprove
	case strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/reject"):
		return scopeReject
	case path == "/undo" || (strings.HasPrefix(path, "/plans/") && strings.HasSuffix(path, "/undo")):
		return scopeUndo
	case strings.HasPrefix(path, "/jobs/") && strings.HasSuffix(path, "/cancel"):
		return scopeCancel
	default:
		return scopeRun
	}
}

func scopeSet(scopes []string) map[string]struct{} {
	out := make(map[string]struct{})
	for _, scope := range normalizeScopes(scopes) {
		out[scope] = struct{}{}
	}
	return out
}

func normalizeScopes(scopes []string) []string {
	if len(scopes) == 0 {
		return []string{scopeRead}
	}
	seen := make(map[string]struct{})
	out := make([]string, 0, len(scopes))
	for _, scope := range scopes {
		item := strings.TrimSpace(strings.ToLower(scope))
		if item == "" {
			continue
		}
		if _, ok := seen[item]; ok {
			continue
		}
		seen[item] = struct{}{}
		out = append(out, item)
	}
	if len(out) == 0 {
		return []string{scopeRead}
	}
	return out
}

func validateScopes(scopes []string) error {
	if len(scopes) == 0 {
		return nil
	}
	unknown := make([]string, 0)
	for _, scope := range scopes {
		if _, ok := bridgeScopeSet[scope]; ok {
			continue
		}
		unknown = append(unknown, scope)
	}
	if len(unknown) == 0 {
		return nil
	}
	return fmt.Errorf("unknown scope(s): %s", strings.Join(unknown, ", "))
}

func generateSessionID() (string, error) {
	buf := make([]byte, 12)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}

func signSessionBody(payloadB64 string, key string) string {
	mac := hmac.New(sha256.New, []byte(key))
	_, _ = mac.Write([]byte(payloadB64))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func extractRequestToken(r *http.Request) string {
	header := strings.TrimSpace(r.Header.Get("Authorization"))
	if strings.HasPrefix(strings.ToLower(header), "bearer ") {
		value := strings.TrimSpace(header[len("Bearer "):])
		if value != "" {
			return value
		}
	}
	if r.URL.Path == "/ws" {
		return strings.TrimSpace(r.URL.Query().Get("token"))
	}
	return ""
}

func (h *Handler) handleIssueSessionToken(body []byte, auth authContext, requestID string) (map[string]any, error) {
	payload := map[string]any{}
	if len(bytesTrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &payload); err != nil {
			return nil, fmt.Errorf("request body must be valid JSON object")
		}
	}

	subject := auth.Subject
	if value := strings.TrimSpace(toString(payload["subject"])); value != "" {
		subject = value
	}

	deviceID := auth.DeviceID
	if value := strings.TrimSpace(toString(payload["device_id"])); value != "" {
		deviceID = value
	}
	if len(h.allowedDevices) > 0 && deviceID == "" {
		return nil, fmt.Errorf("'device_id' is required when device allowlist is enabled")
	}
	if len(h.allowedDevices) > 0 && deviceID != "" {
		if _, ok := h.allowedDevices[deviceID]; !ok {
			return nil, fmt.Errorf("device_id is not in allowed list")
		}
	}

	ttlSeconds := int(h.cfg.SessionTokenTTL.Seconds())
	if rawTTL := toInt(payload["ttl_seconds"]); rawTTL > 0 {
		ttlSeconds = rawTTL
	}

	scopes := extractScopes(payload["scopes"])
	if len(scopes) == 0 {
		scopes = []string{scopeRead, scopeRun, scopePlan, scopeApprove, scopeReject, scopeUndo, scopeCancel}
	}
	if err := validateScopes(scopes); err != nil {
		return nil, err
	}
	token, claims, err := h.issueSessionToken(subject, scopes, deviceID, ttlSeconds)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"token":      token,
		"token_type": "session",
		"subject":    claims.Sub,
		"session_id": claims.JTI,
		"scopes":     claims.Scopes,
		"device_id":  claims.DeviceID,
		"expires_at": claims.Exp,
		"issued_at":  claims.Iat,
		"request_id": requestID,
	}, nil
}

func (h *Handler) handleRevokeSessionToken(body []byte, requestID string) (map[string]any, error) {
	payload := map[string]any{}
	if len(bytesTrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &payload); err != nil {
			return nil, fmt.Errorf("request body must be valid JSON object")
		}
	}
	token := strings.TrimSpace(toString(payload["token"]))
	sessionID := strings.TrimSpace(toString(payload["session_id"]))
	subject := ""
	expiresAt := int64(0)
	via := "session_id"

	if token != "" {
		claims, err := h.verifySessionToken(token)
		if err != nil {
			return nil, fmt.Errorf("invalid session token")
		}
		sessionID = strings.TrimSpace(claims.JTI)
		if sessionID == "" {
			return nil, fmt.Errorf("session token is not revocable")
		}
		subject = claims.Sub
		expiresAt = claims.Exp
		via = "token"
	} else if sessionID == "" {
		return nil, fmt.Errorf("'token' or 'session_id' is required")
	}

	if expiresAt == 0 {
		expiresAt = int64(toInt(payload["expires_at"]))
	}
	now := time.Now().Unix()
	if expiresAt <= now {
		expiresAt = now + 24*3600
	}
	alreadyRevoked, err := h.revokeSession(sessionID, expiresAt)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"revoked":         true,
		"already_revoked": alreadyRevoked,
		"session_id":      sessionID,
		"subject":         subject,
		"expires_at":      expiresAt,
		"via":             via,
		"request_id":      requestID,
	}, nil
}

func extractScopes(value any) []string {
	switch v := value.(type) {
	case []any:
		out := make([]string, 0, len(v))
		for _, item := range v {
			text := strings.TrimSpace(toString(item))
			if text != "" {
				out = append(out, text)
			}
		}
		return normalizeScopes(out)
	case []string:
		return normalizeScopes(v)
	case string:
		items := strings.Split(v, ",")
		return normalizeScopes(items)
	default:
		return nil
	}
}

func toString(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprintf("%v", value)
}

func toInt(value any) int {
	switch v := value.(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	case json.Number:
		if parsed, err := v.Int64(); err == nil {
			return int(parsed)
		}
	case string:
		if parsed, err := strconv.Atoi(strings.TrimSpace(v)); err == nil {
			return parsed
		}
	}
	return 0
}

func bytesTrimSpace(value []byte) []byte {
	return []byte(strings.TrimSpace(string(value)))
}

func (h *Handler) revokeSession(sessionID string, expiresAt int64) (bool, error) {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		return false, nil
	}
	now := time.Now().Unix()
	h.revokedSessionsMu.Lock()
	defer h.revokedSessionsMu.Unlock()
	h.pruneExpiredRevocationsLocked(now)
	currentExpiry, exists := h.revokedSessions[sessionID]
	alreadyRevoked := exists && currentExpiry > now
	previousExpiry := currentExpiry
	h.revokedSessions[sessionID] = expiresAt
	if err := persistRevocationEntries(strings.TrimSpace(h.cfg.RevocationStorePath), h.revokedSessions); err != nil {
		if exists {
			h.revokedSessions[sessionID] = previousExpiry
		} else {
			delete(h.revokedSessions, sessionID)
		}
		return false, fmt.Errorf("failed to persist session revocation: %w", err)
	}
	return alreadyRevoked, nil
}

func (h *Handler) isSessionRevoked(sessionID string, now int64) bool {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		return false
	}
	h.revokedSessionsMu.RLock()
	expiresAt, exists := h.revokedSessions[sessionID]
	h.revokedSessionsMu.RUnlock()
	if !exists {
		return false
	}
	if expiresAt > 0 && expiresAt <= now {
		h.revokedSessionsMu.Lock()
		if current, ok := h.revokedSessions[sessionID]; ok && current <= now {
			delete(h.revokedSessions, sessionID)
		}
		h.revokedSessionsMu.Unlock()
		return false
	}
	return true
}

func (h *Handler) pruneExpiredRevocationsLocked(now int64) {
	for sessionID, expiresAt := range h.revokedSessions {
		if expiresAt > 0 && expiresAt <= now {
			delete(h.revokedSessions, sessionID)
		}
	}
}

func loadRevocationEntries(path string, now int64) (map[string]int64, error) {
	out := make(map[string]int64)
	path = strings.TrimSpace(path)
	if path == "" {
		return out, nil
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return out, nil
		}
		return nil, err
	}
	payload := revocationStorePayload{}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, err
	}
	for sessionID, expiresAt := range payload.RevokedSessions {
		trimmed := strings.TrimSpace(sessionID)
		if trimmed == "" {
			continue
		}
		if expiresAt > 0 && expiresAt <= now {
			continue
		}
		out[trimmed] = expiresAt
	}
	return out, nil
}

func persistRevocationEntries(path string, entries map[string]int64) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil
	}
	payload := revocationStorePayload{
		Version:         1,
		RevokedSessions: entries,
	}
	encoded, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, encoded, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}
