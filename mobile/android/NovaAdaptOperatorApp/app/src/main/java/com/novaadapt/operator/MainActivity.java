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
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.textfield.TextInputEditText;
import com.google.android.material.textview.MaterialTextView;

public class MainActivity extends AppCompatActivity {
    private View onboardingScroll;
    private TextInputEditText pairingPayloadInput;
    private MaterialTextView pairingSummaryView;
    private MaterialTextView pairingStatusView;
    private WebView webView;
    private boolean consoleReady = false;
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
        MaterialButton importPairingButton = findViewById(R.id.import_pairing_button);
        MaterialButton pasteClipboardButton = findViewById(R.id.paste_clipboard_button);
        MaterialButton openSettingsButton = findViewById(R.id.open_settings_button);
        webView = findViewById(R.id.console_webview);
        configureWebView();

        importPairingButton.setOnClickListener((view) -> importPairingPayload(textOf(pairingPayloadInput), "manual import"));
        pasteClipboardButton.setOnClickListener((view) -> importClipboardPayload());
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
        pairingSummaryView.setText(getString(R.string.pairing_summary));
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

    private String textOf(TextInputEditText input) {
        return input.getText() == null ? "" : input.getText().toString().trim();
    }

    private boolean isDebuggableBuild() {
        return (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
    }
}
