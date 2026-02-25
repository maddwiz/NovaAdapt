package relay

import (
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestNewHandlerRejectsPartialCoreClientCertConfig(t *testing.T) {
	_, err := NewHandler(
		Config{
			CoreBaseURL:        "https://core.example.com",
			BridgeToken:        "secret",
			CoreClientCertFile: "/tmp/bridge-client.crt",
		},
	)
	if err == nil {
		t.Fatalf("expected error for partial client cert configuration")
	}
	if !strings.Contains(err.Error(), "both core client cert and key files must be provided together") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestNewHandlerRejectsMissingCoreCAFile(t *testing.T) {
	_, err := NewHandler(
		Config{
			CoreBaseURL: "https://core.example.com",
			BridgeToken: "secret",
			CoreCAFile:  "/tmp/non-existent-core-ca.pem",
		},
	)
	if err == nil {
		t.Fatalf("expected error for missing core CA file")
	}
	if !strings.Contains(err.Error(), "failed to read core CA file") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestHealthDeepHTTPSFailsWithoutTrustedCA(t *testing.T) {
	core := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			_, _ = w.Write([]byte(`{"ok":true}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer core.Close()

	h, err := NewHandler(
		Config{
			CoreBaseURL: core.URL,
			BridgeToken: "secret",
			Timeout:     5 * time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health?deep=1", nil)
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadGateway {
		t.Fatalf("expected 502 got %d body=%s", rr.Code, rr.Body.String())
	}
}

func TestHealthDeepHTTPSWithCustomCAFile(t *testing.T) {
	core := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			_, _ = w.Write([]byte(`{"ok":true}`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer core.Close()

	tempDir := t.TempDir()
	cert := core.Certificate()
	if cert == nil {
		t.Fatalf("expected TLS server certificate")
	}
	caPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Raw})
	caFile := filepath.Join(tempDir, "core-ca.pem")
	if err := os.WriteFile(caFile, caPEM, 0o600); err != nil {
		t.Fatalf("write core ca file: %v", err)
	}

	h, err := NewHandler(
		Config{
			CoreBaseURL: core.URL,
			BridgeToken: "secret",
			Timeout:     5 * time.Second,
			CoreCAFile:  caFile,
		},
	)
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
		t.Fatalf("unmarshal response: %v", err)
	}
	corePayload, ok := payload["core"].(map[string]any)
	if !ok {
		t.Fatalf("expected core payload: %#v", payload)
	}
	if reachable, ok := corePayload["reachable"].(bool); !ok || !reachable {
		t.Fatalf("expected reachable=true: %#v", corePayload)
	}
}
