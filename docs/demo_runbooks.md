# Demo Runbooks

These runbooks are the release-grade operator demos for NovaAdapt's control-anything surface.

## 1. Vision Desktop Demo

Goal:
- Show NovaAdapt grounding a random desktop app from a screenshot and previewing or executing the next action.

Prep:
- start core and bridge
- capture a fresh desktop screenshot that contains the target UI
- verify `novaadapt directshell-check`

Command:

```bash
./scripts/demo_vision_desktop.sh /absolute/path/to/screenshot.png
```

Optional live execute:

```bash
NOVAADAPT_DEMO_EXECUTE=1 ./scripts/demo_vision_desktop.sh /absolute/path/to/screenshot.png
```

Suggested capture shots:
- starting app state
- console preview result with returned action
- live execution result and artifact preview

## 2. Mobile Banking Demo

Goal:
- Show preview-first mobile control with explicit dangerous-action gates before any sensitive flow runs.

Prep:
- verify Android or iOS mobile runtime readiness with `novaadapt mobile-status`
- for Android direct action mode, set `NOVAADAPT_MOBILE_ACTION_JSON`
- for iOS vision mode, provide a screenshot path

Command:

```bash
./scripts/demo_mobile_banking.sh
```

Optional live execute:

```bash
NOVAADAPT_DEMO_EXECUTE=1 NOVAADAPT_ALLOW_DANGEROUS=1 ./scripts/demo_mobile_banking.sh
```

Suggested capture shots:
- preview response showing blocked or gated action
- operator confirmation moment
- execution result once allow-dangerous is explicitly enabled

## 3. IoT Swarm Demo

Goal:
- Show Home Assistant and direct MQTT control from one operator flow, then optionally queue a swarm bundle.

Prep:
- verify `novaadapt homeassistant-status`
- verify `novaadapt mqtt-status`
- pick a safe device/entity for demo use

Command:

```bash
./scripts/demo_iot_swarm.sh
```

Optional swarm queue:

```bash
NOVAADAPT_QUEUE_SWARM=1 ./scripts/demo_iot_swarm.sh
```

Suggested capture shots:
- entity discovery result
- Home Assistant preview or execution result
- MQTT publish result
- optional queued swarm jobs result

## Capture Checklist

- show branch or release version at the start of the recording
- keep every demo preview-first unless the operator explicitly escalates
- record artifact previews, plan/job ids, and approval prompts
- export terminal logs or screenshots into the release notes package after capture
