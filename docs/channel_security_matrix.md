# Channel Security Matrix

This matrix is the canonical reference for inbound verification and webhook posture across NovaAdapt channels.

## Core rules

- All channels support optional `NOVAADAPT_CHANNEL_<CHANNEL>_INBOUND_TOKEN`.
- For channels that expose public webhooks, prefer signature validation over token-only checks.
- Signature strict mode (`*_REQUIRE_SIGNATURE=1`) blocks unsigned inbound payloads.
- `/channels/{name}/health` and `GET /channels` expose a normalized `security` block:
  - `inbound_token_configured`
  - `signature_configured`
  - `signature_required`
  - `direct_webhook_supported`
  - `supported_verification_methods`
  - `recommended_verification_method`

## Matrix

| Channel | Direct webhook payload on `/channels/{name}/inbound` | Supported verification methods | Signature headers | Signature env vars | Notes |
|---|---|---|---|---|---|
| `webchat` | No | `inbound_token` | N/A | N/A | Wrapper payload required (`payload` object). |
| `imessage` | No | `inbound_token` | N/A | N/A | macOS local adapter; wrapper payload required. |
| `whatsapp` | Yes | `inbound_token`, `whatsapp_signature` | `X-Hub-Signature-256` | `NOVAADAPT_CHANNEL_WHATSAPP_APP_SECRET`, `NOVAADAPT_CHANNEL_WHATSAPP_REQUIRE_SIGNATURE` | Uses Meta app-secret HMAC on raw body. |
| `telegram` | Yes | `inbound_token`, `telegram_secret_token`, `telegram_hmac` | `X-Telegram-Bot-Api-Secret-Token` (native), `X-NovaAdapt-Timestamp` + `X-NovaAdapt-Signature` (relay HMAC) | `NOVAADAPT_CHANNEL_TELEGRAM_WEBHOOK_SECRET_TOKEN`, `NOVAADAPT_CHANNEL_TELEGRAM_WEBHOOK_SIGNING_SECRET`, `NOVAADAPT_CHANNEL_TELEGRAM_REQUIRE_SIGNATURE`, `NOVAADAPT_CHANNEL_TELEGRAM_SIGNATURE_MAX_AGE_SECONDS` | Supports native Telegram secret-token verification and relay HMAC mode. |
| `discord` | Yes | `inbound_token`, `discord_ed25519`, `webhook_hmac` | `X-Signature-Ed25519` + `X-Signature-Timestamp` (interactions), `X-NovaAdapt-Timestamp` + `X-NovaAdapt-Signature` (relay HMAC) | `NOVAADAPT_CHANNEL_DISCORD_INTERACTIONS_PUBLIC_KEY`, `NOVAADAPT_CHANNEL_DISCORD_WEBHOOK_SIGNING_SECRET`, `NOVAADAPT_CHANNEL_DISCORD_REQUIRE_SIGNATURE`, `NOVAADAPT_CHANNEL_DISCORD_SIGNATURE_MAX_AGE_SECONDS` | Ed25519 verification requires `cryptography`. |
| `slack` | Yes | `inbound_token`, `slack_signature` | `X-Slack-Request-Timestamp`, `X-Slack-Signature` | `NOVAADAPT_CHANNEL_SLACK_SIGNING_SECRET`, `NOVAADAPT_CHANNEL_SLACK_REQUIRE_SIGNATURE`, `NOVAADAPT_CHANNEL_SLACK_SIGNATURE_MAX_AGE_SECONDS` | Slack URL verification (`type=url_verification`) returns `challenge`. |
| `signal` | Yes | `inbound_token`, `signal_hmac` | `X-Signal-Timestamp`, `X-Signal-Signature` (or `X-NovaAdapt-*`) | `NOVAADAPT_CHANNEL_SIGNAL_WEBHOOK_SIGNING_SECRET`, `NOVAADAPT_CHANNEL_SIGNAL_REQUIRE_SIGNATURE`, `NOVAADAPT_CHANNEL_SIGNAL_SIGNATURE_MAX_AGE_SECONDS` | For signal-cli relay/webhook deployments. |
| `teams` | No | `inbound_token` | N/A | N/A | Wrapper payload required. |
| `googlechat` | No | `inbound_token` | N/A | N/A | Wrapper payload required. |
| `matrix` | No | `inbound_token` | N/A | N/A | Wrapper payload required. |

## Recommended production posture

1. Set inbound tokens for all enabled channels.
2. Enable signature validation for public webhook channels (`whatsapp`, `telegram`, `discord`, `slack`, `signal`).
3. Enable strict signature mode for internet-exposed webhook endpoints.
4. Monitor `GET /channels` and alert when `security.signature_configured=false` on public webhook channels.
