package com.novaadapt.operator;

import android.net.Uri;

import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.Locale;

final class PairingManifest {
    final String bridgeHttpUrl;
    final String wsUrl;
    final String token;
    final String adminToken;
    final String deviceId;
    final boolean autoConnect;
    final String subject;

    private PairingManifest(
            String bridgeHttpUrl,
            String wsUrl,
            String token,
            String adminToken,
            String deviceId,
            boolean autoConnect,
            String subject
    ) {
        this.bridgeHttpUrl = bridgeHttpUrl;
        this.wsUrl = wsUrl;
        this.token = token;
        this.adminToken = adminToken;
        this.deviceId = deviceId;
        this.autoConnect = autoConnect;
        this.subject = subject;
    }

    static PairingManifest parse(String rawValue) throws IllegalArgumentException {
        String raw = safe(rawValue, "");
        if (raw.isEmpty()) {
            throw new IllegalArgumentException("pairing payload is empty");
        }
        String decoded = extractManifestJson(raw);
        try {
            JSONObject payload = new JSONObject(decoded);
            if (payload.has("manifest") && payload.opt("manifest") instanceof JSONObject) {
                payload = payload.getJSONObject("manifest");
            }
            String bridgeHttpUrl = safe(payload.optString("bridge_http_url"), "");
            String wsUrl = safe(payload.optString("ws_url"), "");
            String token = safe(payload.optString("token"), "");
            String adminToken = safe(payload.optString("admin_token"), token);
            String deviceId = safe(payload.optString("device_id"), "android-operator");
            boolean autoConnect = payload.optBoolean("auto_connect", true);
            String subject = safe(payload.optString("subject"), "NovaAdapt Operator");

            if (bridgeHttpUrl.isEmpty() && !wsUrl.isEmpty()) {
                bridgeHttpUrl = inferBridgeHttpUrl(wsUrl);
            }
            if (wsUrl.isEmpty() && !bridgeHttpUrl.isEmpty()) {
                wsUrl = inferWsUrl(bridgeHttpUrl);
            }
            if (token.isEmpty()) {
                throw new IllegalArgumentException("pairing payload is missing token");
            }
            if (bridgeHttpUrl.isEmpty()) {
                throw new IllegalArgumentException("pairing payload is missing bridge_http_url");
            }
            if (wsUrl.isEmpty()) {
                throw new IllegalArgumentException("pairing payload is missing ws_url");
            }

            return new PairingManifest(
                    bridgeHttpUrl,
                    wsUrl,
                    token,
                    adminToken,
                    deviceId,
                    autoConnect,
                    subject
            );
        } catch (JSONException err) {
            throw new IllegalArgumentException("pairing payload is not valid JSON", err);
        }
    }

    private static String extractManifestJson(String raw) {
        String trimmed = raw.trim();
        if (trimmed.startsWith("{")) {
            return trimmed;
        }
        if (trimmed.startsWith("novaadapt://") || trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            Uri uri = Uri.parse(trimmed);
            String payload = safe(uri.getQueryParameter("payload"), "");
            if (payload.isEmpty()) {
                throw new IllegalArgumentException("pairing link is missing payload");
            }
            return decodeBase64Url(payload);
        }
        return decodeBase64Url(trimmed);
    }

    private static String decodeBase64Url(String value) {
        try {
            byte[] decoded = android.util.Base64.decode(value, android.util.Base64.URL_SAFE | android.util.Base64.NO_WRAP | android.util.Base64.NO_PADDING);
            return new String(decoded, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException err) {
            throw new IllegalArgumentException("pairing code is invalid", err);
        }
    }

    private static String inferBridgeHttpUrl(String rawWsUrl) {
        Uri uri = Uri.parse(rawWsUrl);
        String scheme = safe(uri.getScheme(), "ws").toLowerCase(Locale.US);
        String httpScheme = "wss".equals(scheme) ? "https" : "http";
        return uri.buildUpon()
                .scheme(httpScheme)
                .encodedPath("")
                .encodedQuery(null)
                .fragment(null)
                .build()
                .toString()
                .replaceAll("/$", "");
    }

    private static String inferWsUrl(String rawBridgeHttpUrl) {
        Uri uri = Uri.parse(rawBridgeHttpUrl);
        String scheme = safe(uri.getScheme(), "http").toLowerCase(Locale.US);
        String wsScheme = "https".equals(scheme) ? "wss" : "ws";
        return uri.buildUpon()
                .scheme(wsScheme)
                .encodedPath("/ws")
                .encodedQuery(null)
                .fragment(null)
                .build()
                .toString();
    }

    private static String safe(String value, String fallback) {
        String text = value == null ? "" : value.trim();
        return text.isEmpty() ? fallback : text;
    }
}
