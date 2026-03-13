package com.novaadapt.operator;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

final class BridgeDiscovery {
    private static final int DEFAULT_PORT = 9797;
    private static final int CONNECT_TIMEOUT_MS = 275;
    private static final int READ_TIMEOUT_MS = 350;
    private static final int MAX_THREADS = 24;

    private BridgeDiscovery() {}

    static List<Result> discoverNearby() {
        Set<String> candidates = candidateHosts();
        if (candidates.isEmpty()) {
            return Collections.emptyList();
        }

        ExecutorService executor = Executors.newFixedThreadPool(MAX_THREADS);
        CompletionService<Result> completion = new ExecutorCompletionService<>(executor);
        int submitted = 0;
        for (String host : candidates) {
            completion.submit(() -> probe(host));
            submitted++;
        }

        Map<String, Result> found = new LinkedHashMap<>();
        try {
            for (int i = 0; i < submitted; i++) {
                Future<Result> future = completion.take();
                Result result = future.get();
                if (result == null) {
                    continue;
                }
                found.putIfAbsent(result.bridgeHttpUrl, result);
            }
        } catch (Exception ignored) {
            // Partial discovery results are fine; return what we found.
        } finally {
            executor.shutdownNow();
            try {
                executor.awaitTermination(1, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }

        return new ArrayList<>(found.values());
    }

    private static Set<String> candidateHosts() {
        LinkedHashSet<String> hosts = new LinkedHashSet<>();
        hosts.add("10.0.2.2");
        hosts.add("10.0.3.2");
        hosts.add("127.0.0.1");
        hosts.add("localhost");
        hosts.add("novaadapt.local");
        hosts.add("bridge.local");

        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces != null && interfaces.hasMoreElements()) {
                NetworkInterface networkInterface = interfaces.nextElement();
                if (!networkInterface.isUp() || networkInterface.isLoopback() || networkInterface.isVirtual()) {
                    continue;
                }
                Enumeration<InetAddress> addresses = networkInterface.getInetAddresses();
                while (addresses.hasMoreElements()) {
                    InetAddress address = addresses.nextElement();
                    if (!(address instanceof Inet4Address) || !address.isSiteLocalAddress()) {
                        continue;
                    }
                    byte[] bytes = address.getAddress();
                    String self = address.getHostAddress();
                    if (self != null && !self.trim().isEmpty()) {
                        hosts.add(self.trim());
                    }
                    if (bytes.length != 4) {
                        continue;
                    }
                    String base = String.format(
                            Locale.US,
                            "%d.%d.%d.",
                            bytes[0] & 0xff,
                            bytes[1] & 0xff,
                            bytes[2] & 0xff
                    );
                    int selfLast = bytes[3] & 0xff;
                    int[] preferred = new int[]{1, 2, 10, 20, 50, 100, 200, selfLast};
                    for (int last : preferred) {
                        if (last <= 0 || last >= 255) {
                            continue;
                        }
                        hosts.add(base + last);
                    }
                    for (int last = 1; last < 255; last++) {
                        hosts.add(base + last);
                    }
                }
            }
        } catch (Exception ignored) {
            // Return best-effort default candidates.
        }
        return hosts;
    }

    private static Result probe(String host) {
        String cleanHost = host == null ? "" : host.trim();
        if (cleanHost.isEmpty()) {
            return null;
        }

        String httpUrl = "http://" + cleanHost + ":" + DEFAULT_PORT;
        HttpURLConnection connection = null;
        try {
            URL url = new URL(httpUrl + "/health");
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setUseCaches(false);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("Accept", "application/json");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                return null;
            }
            String body = readAll(connection.getInputStream());
            if (body == null || body.trim().isEmpty()) {
                return null;
            }
            JSONObject payload = new JSONObject(body);
            String service = payload.optString("service", "");
            JSONObject bridge = payload.optJSONObject("bridge");
            if (!"novaadapt-bridge-go".equals(service) && bridge == null) {
                return null;
            }
            return new Result(
                    cleanHost,
                    httpUrl,
                    "ws://" + cleanHost + ":" + DEFAULT_PORT + "/ws",
                    service.isEmpty() ? "novaadapt-bridge" : service
            );
        } catch (Exception ignored) {
            return null;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private static String readAll(InputStream stream) throws Exception {
        try (InputStream in = stream; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }

    static final class Result {
        final String host;
        final String bridgeHttpUrl;
        final String wsUrl;
        final String service;

        Result(String host, String bridgeHttpUrl, String wsUrl, String service) {
            this.host = host;
            this.bridgeHttpUrl = bridgeHttpUrl;
            this.wsUrl = wsUrl;
            this.service = service;
        }
    }
}
