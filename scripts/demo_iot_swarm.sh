#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${NOVAADAPT_CONFIG_PATH:-$ROOT_DIR/config/models.example.json}"
ENTITY_ID="${NOVAADAPT_HA_ENTITY_ID:-light.office}"
HA_DOMAIN="${NOVAADAPT_HA_DOMAIN:-light}"
HA_SERVICE="${NOVAADAPT_HA_SERVICE:-turn_on}"
MQTT_TOPIC="${NOVAADAPT_MQTT_TOPIC:-novaadapt/demo/status}"
MQTT_PAYLOAD="${NOVAADAPT_MQTT_PAYLOAD:-{"state":"running"}}"
QUEUE_SWARM="${NOVAADAPT_QUEUE_SWARM:-0}"
CORE_URL="${NOVAADAPT_CORE_URL:-http://127.0.0.1:8787}"
CORE_TOKEN="${NOVAADAPT_CORE_TOKEN:-}"
EXECUTE_FLAG="${NOVAADAPT_DEMO_EXECUTE:-0}"
ALLOW_DANGEROUS_FLAG="${NOVAADAPT_ALLOW_DANGEROUS:-0}"

PYTHONPATH="$ROOT_DIR/core:$ROOT_DIR/shared${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

echo "[iot] discovering Home Assistant entities"
python3 -m novaadapt_core.cli homeassistant-discover --config "$CONFIG_PATH" --domain "$HA_DOMAIN" --limit 10

echo "[iot] preview or execute Home Assistant service"
ha_cmd=(
  python3 -m novaadapt_core.cli homeassistant-action
  --config "$CONFIG_PATH"
  --action-json "{\"type\":\"ha_service\",\"domain\":\"$HA_DOMAIN\",\"service\":\"$HA_SERVICE\",\"entity_id\":\"$ENTITY_ID\"}"
)
if [[ "$EXECUTE_FLAG" == "1" ]]; then
  ha_cmd+=(--execute)
fi
if [[ "$ALLOW_DANGEROUS_FLAG" == "1" ]]; then
  ha_cmd+=(--allow-dangerous)
fi
"${ha_cmd[@]}"

echo "[iot] preview or publish MQTT message"
mqtt_cmd=(
  python3 -m novaadapt_core.cli mqtt-publish
  --config "$CONFIG_PATH"
  --topic "$MQTT_TOPIC"
  --payload "$MQTT_PAYLOAD"
)
if [[ "$EXECUTE_FLAG" == "1" ]]; then
  mqtt_cmd+=(--execute)
fi
if [[ "$ALLOW_DANGEROUS_FLAG" == "1" ]]; then
  mqtt_cmd+=(--allow-dangerous)
fi
"${mqtt_cmd[@]}"

if [[ "$QUEUE_SWARM" == "1" ]]; then
  echo "[iot] queueing optional swarm objective bundle"
  NOVAADAPT_DEMO_CORE_URL="$CORE_URL" NOVAADAPT_DEMO_CORE_TOKEN="$CORE_TOKEN" \
  NOVAADAPT_DEMO_ENTITY_ID="$ENTITY_ID" NOVAADAPT_DEMO_TOPIC="$MQTT_TOPIC" \
  python3 - <<'PY'
from __future__ import annotations

import json
import os
from novaadapt_shared.api_client import NovaAdaptAPIClient

base_url = os.environ.get("NOVAADAPT_DEMO_CORE_URL", "http://127.0.0.1:8787")
token = os.environ.get("NOVAADAPT_DEMO_CORE_TOKEN") or None
entity_id = os.environ.get("NOVAADAPT_DEMO_ENTITY_ID", "light.office")
topic = os.environ.get("NOVAADAPT_DEMO_TOPIC", "novaadapt/demo/status")
client = NovaAdaptAPIClient(base_url=base_url, token=token)
resp = client.run_swarm(
    [
        f"Use IoT control to operate {entity_id} safely and summarize the result.",
        f"Publish a status update to MQTT topic {topic} and report the broker response.",
    ],
    strategy="decompose",
    execute=False,
    auto_repair_attempts=1,
    max_agents=2,
)
print(json.dumps(resp, indent=2))
PY
fi
