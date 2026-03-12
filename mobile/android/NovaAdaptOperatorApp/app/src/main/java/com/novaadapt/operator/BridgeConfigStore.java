package com.novaadapt.operator;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;

final class BridgeConfigStore {
    private static final String PREFS_NAME = "novaadapt_operator_prefs";
    private static final String KEY_WS_URL = "ws_url";
    private static final String KEY_BRIDGE_HTTP_URL = "bridge_http_url";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_ADMIN_TOKEN = "admin_token";
    private static final String KEY_DEVICE_ID = "device_id";
    private static final String KEY_AUTO_CONNECT = "auto_connect";

    private BridgeConfigStore() {}

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    static String defaultWsUrl() {
        return "ws://127.0.0.1:9797/ws";
    }

    static String defaultBridgeHttpUrl() {
        return "http://127.0.0.1:9797";
    }

    static String getWsUrl(Context context) {
        return prefs(context).getString(KEY_WS_URL, defaultWsUrl());
    }

    static String getBridgeHttpUrl(Context context) {
        return prefs(context).getString(KEY_BRIDGE_HTTP_URL, defaultBridgeHttpUrl());
    }

    static String getToken(Context context) {
        return prefs(context).getString(KEY_TOKEN, "");
    }

    static String getAdminToken(Context context) {
        return prefs(context).getString(KEY_ADMIN_TOKEN, "");
    }

    static String getDeviceId(Context context) {
        return prefs(context).getString(KEY_DEVICE_ID, "android-operator");
    }

    static boolean isAutoConnectEnabled(Context context) {
        return prefs(context).getBoolean(KEY_AUTO_CONNECT, true);
    }

    static boolean hasCompleteConfiguration(Context context) {
        return !getWsUrl(context).isEmpty()
                && !getBridgeHttpUrl(context).isEmpty()
                && !getToken(context).isEmpty();
    }

    static void applyPairingManifest(Context context, PairingManifest manifest) {
        save(
                context,
                manifest.wsUrl,
                manifest.bridgeHttpUrl,
                manifest.token,
                manifest.adminToken,
                manifest.deviceId,
                manifest.autoConnect
        );
    }

    static void save(
            Context context,
            String wsUrl,
            String bridgeHttpUrl,
            String token,
            String adminToken,
            String deviceId,
            boolean autoConnect
    ) {
        prefs(context)
                .edit()
                .putString(KEY_WS_URL, safe(wsUrl, defaultWsUrl()))
                .putString(KEY_BRIDGE_HTTP_URL, safe(bridgeHttpUrl, defaultBridgeHttpUrl()))
                .putString(KEY_TOKEN, safe(token, ""))
                .putString(KEY_ADMIN_TOKEN, safe(adminToken, ""))
                .putString(KEY_DEVICE_ID, safe(deviceId, "android-operator"))
                .putBoolean(KEY_AUTO_CONNECT, autoConnect)
                .apply();
    }

    static void reset(Context context) {
        save(context, defaultWsUrl(), defaultBridgeHttpUrl(), "", "", "android-operator", true);
    }

    static String buildConsoleUrl(Context context) {
        Uri.Builder builder = Uri.parse("file:///android_asset/realtime_console.html").buildUpon();
        builder.appendQueryParameter("ws_url", getWsUrl(context));
        builder.appendQueryParameter("bridge_http_url", getBridgeHttpUrl(context));
        String token = getToken(context);
        String adminToken = getAdminToken(context);
        String deviceId = getDeviceId(context);
        if (!token.isEmpty()) {
            builder.appendQueryParameter("token", token);
        }
        if (!adminToken.isEmpty()) {
            builder.appendQueryParameter("admin_token", adminToken);
        }
        if (!deviceId.isEmpty()) {
            builder.appendQueryParameter("device_id", deviceId);
        }
        if (isAutoConnectEnabled(context)) {
            builder.appendQueryParameter("auto_connect", "1");
        }
        return builder.build().toString();
    }

    private static String safe(String value, String fallback) {
        String text = value == null ? "" : value.trim();
        return text.isEmpty() ? fallback : text;
    }
}
