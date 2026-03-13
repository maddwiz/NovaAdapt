package com.novaadapt.operator;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

@RunWith(RobolectricTestRunner.class)
public class PairingManifestTest {
    @Test
    public void parseRawJsonManifest() {
        PairingManifest manifest = PairingManifest.parse("{\"bridge_http_url\":\"http://192.168.1.20:9797\",\"ws_url\":\"ws://192.168.1.20:9797/ws\",\"token\":\"operator-token\",\"admin_token\":\"admin-token\",\"device_id\":\"pixel-1\",\"subject\":\"NovaRemote\",\"auto_connect\":true}");

        assertEquals("http://192.168.1.20:9797", manifest.bridgeHttpUrl);
        assertEquals("ws://192.168.1.20:9797/ws", manifest.wsUrl);
        assertEquals("operator-token", manifest.token);
        assertEquals("admin-token", manifest.adminToken);
        assertEquals("pixel-1", manifest.deviceId);
        assertEquals("NovaRemote", manifest.subject);
        assertTrue(manifest.autoConnect);
    }

    @Test
    public void parseDeepLinkPayload() {
        String payload = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                        "{\"bridge_http_url\":\"http://bridge.local:9797\",\"ws_url\":\"ws://bridge.local:9797/ws\",\"token\":\"pair-token\"}".getBytes(StandardCharsets.UTF_8)
                );

        PairingManifest manifest = PairingManifest.parse("novaadapt://pair?payload=" + payload);

        assertEquals("http://bridge.local:9797", manifest.bridgeHttpUrl);
        assertEquals("ws://bridge.local:9797/ws", manifest.wsUrl);
        assertEquals("pair-token", manifest.token);
        assertEquals("pair-token", manifest.adminToken);
    }

    @Test
    public void inferMissingWsOrHttpValues() {
        PairingManifest fromWs = PairingManifest.parse("{\"ws_url\":\"wss://bridge.example.com/ws\",\"token\":\"pair-token\"}");
        assertEquals("https://bridge.example.com", fromWs.bridgeHttpUrl);

        PairingManifest fromHttp = PairingManifest.parse("{\"bridge_http_url\":\"http://bridge.example.com:9797\",\"token\":\"pair-token\"}");
        assertEquals("ws://bridge.example.com:9797/ws", fromHttp.wsUrl);
    }
}
