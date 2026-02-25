package main

import (
	"context"
	"errors"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/maddwiz/novaadapt/bridge/internal/relay"
)

func main() {
	host := flag.String("host", envOrDefault("NOVAADAPT_BRIDGE_HOST", "127.0.0.1"), "Bridge host")
	port := flag.Int("port", envOrDefaultInt("NOVAADAPT_BRIDGE_PORT", 9797), "Bridge port")
	coreURL := flag.String("core-url", envOrDefault("NOVAADAPT_CORE_URL", "http://127.0.0.1:8787"), "Core API URL")
	bridgeToken := flag.String("bridge-token", os.Getenv("NOVAADAPT_BRIDGE_TOKEN"), "Bearer token required for bridge clients")
	coreToken := flag.String("core-token", os.Getenv("NOVAADAPT_CORE_TOKEN"), "Bearer token used when calling core API")
	sessionSigningKey := flag.String(
		"session-signing-key",
		os.Getenv("NOVAADAPT_BRIDGE_SESSION_SIGNING_KEY"),
		"HMAC key for issuing/verifying scoped bridge session tokens (defaults to bridge token when unset)",
	)
	sessionTokenTTL := flag.Int(
		"session-token-ttl-seconds",
		envOrDefaultInt("NOVAADAPT_BRIDGE_SESSION_TTL_SECONDS", 900),
		"Default ttl for issued bridge session tokens",
	)
	allowedDeviceIDs := flag.String(
		"allowed-device-ids",
		envOrDefault("NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS", ""),
		"Comma-separated trusted X-Device-ID values (optional)",
	)
	timeout := flag.Int("timeout", envOrDefaultInt("NOVAADAPT_BRIDGE_TIMEOUT", 30), "Core request timeout seconds")
	logRequests := flag.Bool("log-requests", envOrDefaultBool("NOVAADAPT_BRIDGE_LOG_REQUESTS", true), "Enable per-request bridge logs")
	flag.Parse()

	handler, err := relay.NewHandler(relay.Config{
		CoreBaseURL:       *coreURL,
		BridgeToken:       *bridgeToken,
		CoreToken:         *coreToken,
		SessionSigningKey: *sessionSigningKey,
		SessionTokenTTL:   time.Duration(max(60, *sessionTokenTTL)) * time.Second,
		AllowedDeviceIDs:  parseCSV(*allowedDeviceIDs),
		Timeout:           time.Duration(max(1, *timeout)) * time.Second,
		LogRequests:       *logRequests,
		Logger:            log.Default(),
	})
	if err != nil {
		log.Fatalf("failed to initialize relay: %v", err)
	}

	addr := *host + ":" + strconv.Itoa(*port)
	server := &http.Server{Addr: addr, Handler: handler}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		log.Printf("novaadapt-bridge-go listening on %s -> core %s", addr, *coreURL)
		errCh <- server.ListenAndServe()
	}()

	select {
	case <-ctx.Done():
		log.Printf("shutdown signal received")
	case err := <-errCh:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
		return
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("shutdown error: %v", err)
	}
	log.Printf("bridge stopped")
}

func envOrDefault(key, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}

func envOrDefaultInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func envOrDefaultBool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func parseCSV(value string) []string {
	if value == "" {
		return nil
	}
	items := make([]string, 0)
	for _, part := range strings.Split(value, ",") {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" {
			continue
		}
		items = append(items, trimmed)
	}
	return items
}
