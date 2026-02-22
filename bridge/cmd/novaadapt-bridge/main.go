package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/maddwiz/novaadapt/bridge/internal/relay"
)

func main() {
	host := flag.String("host", envOrDefault("NOVAADAPT_BRIDGE_HOST", "127.0.0.1"), "Bridge host")
	port := flag.Int("port", envOrDefaultInt("NOVAADAPT_BRIDGE_PORT", 9797), "Bridge port")
	coreURL := flag.String("core-url", envOrDefault("NOVAADAPT_CORE_URL", "http://127.0.0.1:8787"), "Core API URL")
	bridgeToken := flag.String("bridge-token", os.Getenv("NOVAADAPT_BRIDGE_TOKEN"), "Bearer token required for bridge clients")
	coreToken := flag.String("core-token", os.Getenv("NOVAADAPT_CORE_TOKEN"), "Bearer token used when calling core API")
	timeout := flag.Int("timeout", envOrDefaultInt("NOVAADAPT_BRIDGE_TIMEOUT", 30), "Core request timeout seconds")
	flag.Parse()

	handler, err := relay.NewHandler(relay.Config{
		CoreBaseURL: *coreURL,
		BridgeToken: *bridgeToken,
		CoreToken:   *coreToken,
		Timeout:     time.Duration(max(1, *timeout)) * time.Second,
	})
	if err != nil {
		log.Fatalf("failed to initialize relay: %v", err)
	}

	addr := *host + ":" + strconv.Itoa(*port)
	log.Printf("novaadapt-bridge-go listening on %s -> core %s", addr, *coreURL)
	if err := http.ListenAndServe(addr, handler); err != nil {
		log.Fatalf("server error: %v", err)
	}
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

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
