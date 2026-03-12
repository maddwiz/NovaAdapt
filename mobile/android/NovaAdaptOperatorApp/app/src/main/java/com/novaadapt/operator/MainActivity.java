package com.novaadapt.operator;

import android.annotation.SuppressLint;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.os.Build;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.Toast;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.annotation.NonNull;
import androidx.activity.result.ActivityResultLauncher;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;
import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.textfield.TextInputEditText;
import com.google.android.material.textview.MaterialTextView;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity {
    private ActivityResultLauncher<ScanOptions> qrScanLauncher;
    private View onboardingScroll;
    private TextInputEditText pairingPayloadInput;
    private MaterialTextView pairingSummaryView;
    private MaterialTextView pairingStatusView;
    private MaterialTextView discoveryStatusView;
    private WebView webView;
    private ExecutorService backgroundExecutor;
    private boolean consoleReady = false;
    private boolean discoveryInFlight = false;
    private String discoveredBridgeHttpUrl = "";
    private String lastLoadedUrl = "";

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        onboardingScroll = findViewById(R.id.onboarding_scroll);
        pairingPayloadInput = findViewById(R.id.pairing_payload_input);
        pairingSummaryView = findViewById(R.id.pairing_summary);
        pairingStatusView = findViewById(R.id.pairing_status);
        discoveryStatusView = findViewById(R.id.discovery_status);
        MaterialButton importPairingButton = findViewById(R.id.import_pairing_button);
        MaterialButton pasteClipboardButton = findViewById(R.id.paste_clipboard_button);
        MaterialButton scanQrButton = findViewById(R.id.scan_qr_button);
        MaterialButton discoverBridgeButton = findViewById(R.id.discover_bridge_button);
        MaterialButton openSettingsButton = findViewById(R.id.open_settings_button);
        webView = findViewById(R.id.console_webview);
        backgroundExecutor = Executors.newSingleThreadExecutor();
        qrScanLauncher = registerForActivityResult(new ScanContract(), result -> {
            String contents = result == null ? "" : result.getContents();
            if (contents == null || contents.trim().isEmpty()) {
                setPairingStatus(getString(R.string.pairing_status_scan_cancelled), false);
                return;
            }
            pairingPayloadInput.setText(contents);
            importPairingPayload(contents, "qr scan");
        });
        configureWebView();

        importPairingButton.setOnClickListener((view) -> importPairingPayload(textOf(pairingPayloadInput), "manual import"));
        pasteClipboardButton.setOnClickListener((view) -> importClipboardPayload());
        scanQrButton.setOnClickListener((view) -> launchQrScanner());
        discoverBridgeButton.setOnClickListener((view) -> discoverNearbyBridge());
        openSettingsButton.setOnClickListener((view) -> startActivity(new Intent(this, SettingsActivity.class)));

        boolean consumedIntent = consumePairingIntent(getIntent());
        if (!consumedIntent) {
            refreshConsoleState(true);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshConsoleState(false);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (!consumePairingIntent(intent)) {
            refreshConsoleState(true);
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.main_actions, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        int itemId = item.getItemId();
        if (itemId == R.id.action_settings) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        if (itemId == R.id.action_reload) {
            refreshConsoleState(true);
            return true;
        }
        if (itemId == R.id.action_reconnect) {
            if (consoleReady) {
                webView.evaluateJavascript(
                        "if (typeof connect === 'function') { try { connect(); } catch (err) { console.error(err); } }",
                        null
                );
            } else {
                setPairingStatus(getString(R.string.pairing_status_waiting), false);
            }
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (consoleReady && webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (backgroundExecutor != null) {
            backgroundExecutor.shutdownNow();
        }
        super.onDestroy();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setMediaPlaybackRequiresUserGesture(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN) {
            settings.setAllowFileAccessFromFileURLs(true);
            settings.setAllowUniversalAccessFromFileURLs(true);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }
        WebView.setWebContentsDebuggingEnabled(isDebuggableBuild());
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                lastLoadedUrl = url == null ? "" : url;
            }
        });
    }

    private void loadConsole(boolean forceReload) {
        String url = BridgeConfigStore.buildConsoleUrl(this);
        if (forceReload || !url.equals(lastLoadedUrl)) {
            webView.loadUrl(url);
        }
    }

    private void refreshConsoleState(boolean forceReload) {
        boolean configured = BridgeConfigStore.hasCompleteConfiguration(this);
        consoleReady = configured;
        if (configured) {
            onboardingScroll.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            pairingSummaryView.setText(getString(R.string.pairing_summary_configured, BridgeConfigStore.getBridgeHttpUrl(this)));
            setPairingStatus(
                    getString(R.string.pairing_status_ready, BridgeConfigStore.getDeviceId(this)),
                    true
            );
            loadConsole(forceReload);
            return;
        }
        onboardingScroll.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);
        if (!discoveredBridgeHttpUrl.isEmpty()) {
            pairingSummaryView.setText(getString(R.string.pairing_summary_discovered, discoveredBridgeHttpUrl));
        } else {
            pairingSummaryView.setText(getString(R.string.pairing_summary));
        }
        if (textOf(pairingPayloadInput).isEmpty()) {
            setPairingStatus(getString(R.string.pairing_status_waiting), false);
        }
    }

    private boolean consumePairingIntent(Intent intent) {
        String payload = extractPairingPayload(intent);
        if (payload.isEmpty()) {
            return false;
        }
        pairingPayloadInput.setText(payload);
        return importPairingPayload(payload, "intent import");
    }

    private boolean importPairingPayload(String rawPayload, String source) {
        String payload = rawPayload == null ? "" : rawPayload.trim();
        if (payload.isEmpty()) {
            setPairingStatus(getString(R.string.pairing_status_empty), false);
            return false;
        }
        try {
            PairingManifest manifest = PairingManifest.parse(payload);
            BridgeConfigStore.applyPairingManifest(this, manifest);
            pairingPayloadInput.setText(payload);
            setPairingStatus(
                    getString(R.string.pairing_status_imported, manifest.subject, manifest.deviceId),
                    true
            );
            Toast.makeText(this, getString(R.string.pairing_status_imported, manifest.subject, manifest.deviceId), Toast.LENGTH_SHORT).show();
            refreshConsoleState(true);
            return true;
        } catch (IllegalArgumentException err) {
            setPairingStatus(getString(R.string.pairing_status_invalid, source, err.getMessage()), false);
            Toast.makeText(this, getString(R.string.pairing_status_invalid, source, err.getMessage()), Toast.LENGTH_LONG).show();
            if (!BridgeConfigStore.hasCompleteConfiguration(this)) {
                refreshConsoleState(false);
            }
            return false;
        }
    }

    private void importClipboardPayload() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard == null || !clipboard.hasPrimaryClip()) {
            setPairingStatus(getString(R.string.pairing_status_clipboard_empty), false);
            return;
        }
        ClipData clip = clipboard.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            setPairingStatus(getString(R.string.pairing_status_clipboard_empty), false);
            return;
        }
        CharSequence raw = clip.getItemAt(0).coerceToText(this);
        String payload = raw == null ? "" : raw.toString();
        if (payload.trim().isEmpty()) {
            setPairingStatus(getString(R.string.pairing_status_clipboard_empty), false);
            return;
        }
        pairingPayloadInput.setText(payload);
        importPairingPayload(payload, "clipboard import");
    }

    private void launchQrScanner() {
        try {
            ScanOptions options = new ScanOptions();
            options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
            options.setPrompt(getString(R.string.scan_prompt));
            options.setBeepEnabled(false);
            options.setOrientationLocked(false);
            options.setBarcodeImageEnabled(false);
            qrScanLauncher.launch(options);
        } catch (Exception err) {
            setPairingStatus(getString(R.string.pairing_status_scan_failed, err.getMessage()), false);
        }
    }

    private void discoverNearbyBridge() {
        if (discoveryInFlight || backgroundExecutor == null) {
            return;
        }
        discoveryInFlight = true;
        setDiscoveryStatus(getString(R.string.discovery_status_running), R.color.nova_muted);
        backgroundExecutor.execute(() -> {
            try {
                List<BridgeDiscovery.Result> results = BridgeDiscovery.discoverNearby();
                runOnUiThread(() -> applyDiscoveryResults(results));
            } catch (Exception err) {
                runOnUiThread(() -> {
                    discoveryInFlight = false;
                    setDiscoveryStatus(getString(R.string.discovery_status_failed, err.getMessage()), R.color.nova_warn);
                });
            }
        });
    }

    private void applyDiscoveryResults(List<BridgeDiscovery.Result> results) {
        discoveryInFlight = false;
        if (results == null || results.isEmpty()) {
            discoveredBridgeHttpUrl = "";
            setDiscoveryStatus(getString(R.string.discovery_status_none), R.color.nova_warn);
            refreshConsoleState(false);
            return;
        }
        BridgeDiscovery.Result primary = results.get(0);
        discoveredBridgeHttpUrl = primary.bridgeHttpUrl;
        BridgeConfigStore.saveDiscoveredBridge(this, primary.wsUrl, primary.bridgeHttpUrl);
        if (results.size() == 1) {
            setDiscoveryStatus(getString(R.string.discovery_status_found_one, primary.bridgeHttpUrl), R.color.nova_ok);
        } else {
            setDiscoveryStatus(getString(R.string.discovery_status_found_many, results.size(), primary.bridgeHttpUrl), R.color.nova_ok);
        }
        Toast.makeText(this, discoveryStatusView.getText(), Toast.LENGTH_SHORT).show();
        refreshConsoleState(true);
    }

    private String extractPairingPayload(Intent intent) {
        if (intent == null) {
            return "";
        }
        if (Intent.ACTION_VIEW.equals(intent.getAction())) {
            if (intent.getDataString() != null) {
                return intent.getDataString();
            }
        }
        if (Intent.ACTION_SEND.equals(intent.getAction())) {
            CharSequence extra = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (extra != null) {
                return extra.toString();
            }
        }
        if (intent.getDataString() != null) {
            return intent.getDataString();
        }
        CharSequence extra = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
        return extra == null ? "" : extra.toString();
    }

    private void setPairingStatus(String text, boolean ok) {
        pairingStatusView.setText(text);
        pairingStatusView.setTextColor(ContextCompat.getColor(
                this,
                ok ? R.color.nova_ok : R.color.nova_warn
        ));
    }

    private void setDiscoveryStatus(String text, int colorRes) {
        discoveryStatusView.setText(text);
        discoveryStatusView.setTextColor(ContextCompat.getColor(this, colorRes));
    }

    private String textOf(TextInputEditText input) {
        return input.getText() == null ? "" : input.getText().toString().trim();
    }

    private boolean isDebuggableBuild() {
        return (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
    }
}
