package com.novaadapt.operator;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.content.Context;

import androidx.test.core.app.ApplicationProvider;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

@RunWith(RobolectricTestRunner.class)
public class BridgeConfigStoreTest {
    private Context context;

    @Before
    public void setUp() {
        context = ApplicationProvider.getApplicationContext();
        BridgeConfigStore.reset(context);
    }

    @Test
    public void applyPairingManifestPopulatesStoredValues() {
        PairingManifest manifest = PairingManifest.parse("{\"bridge_http_url\":\"http://192.168.1.50:9797\",\"ws_url\":\"ws://192.168.1.50:9797/ws\",\"token\":\"operator-token\",\"admin_token\":\"admin-token\",\"device_id\":\"pixel-1\",\"auto_connect\":true}");

        BridgeConfigStore.applyPairingManifest(context, manifest);

        assertEquals("http://192.168.1.50:9797", BridgeConfigStore.getBridgeHttpUrl(context));
        assertEquals("ws://192.168.1.50:9797/ws", BridgeConfigStore.getWsUrl(context));
        assertEquals("operator-token", BridgeConfigStore.getToken(context));
        assertEquals("admin-token", BridgeConfigStore.getAdminToken(context));
        assertEquals("pixel-1", BridgeConfigStore.getDeviceId(context));
        assertTrue(BridgeConfigStore.isAutoConnectEnabled(context));
    }

    @Test
    public void discoveredBridgePreservesExistingAuth() {
        BridgeConfigStore.save(
                context,
                "ws://old-host:9797/ws",
                "http://old-host:9797",
                "operator-token",
                "admin-token",
                "pixel-1",
                true
        );

        BridgeConfigStore.saveDiscoveredBridge(context, "ws://new-host:9797/ws", "http://new-host:9797");

        assertEquals("ws://new-host:9797/ws", BridgeConfigStore.getWsUrl(context));
        assertEquals("http://new-host:9797", BridgeConfigStore.getBridgeHttpUrl(context));
        assertEquals("operator-token", BridgeConfigStore.getToken(context));
        assertEquals("admin-token", BridgeConfigStore.getAdminToken(context));
        assertEquals("pixel-1", BridgeConfigStore.getDeviceId(context));
    }

    @Test
    public void consoleUrlIncludesBootstrapParams() {
        BridgeConfigStore.save(
                context,
                "ws://new-host:9797/ws",
                "http://new-host:9797",
                "operator-token",
                "admin-token",
                "pixel-1",
                true
        );

        String url = BridgeConfigStore.buildConsoleUrl(context);
        assertTrue(url.contains("ws_url=ws%3A%2F%2Fnew-host%3A9797%2Fws"));
        assertTrue(url.contains("bridge_http_url=http%3A%2F%2Fnew-host%3A9797"));
        assertTrue(url.contains("token=operator-token"));
        assertTrue(url.contains("admin_token=admin-token"));
        assertTrue(url.contains("device_id=pixel-1"));
        assertTrue(url.contains("auto_connect=1"));
    }
}
