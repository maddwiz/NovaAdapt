package com.novaadapt.operator;

import android.os.Bundle;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.SwitchCompat;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.textfield.TextInputEditText;

public class SettingsActivity extends AppCompatActivity {
    private TextInputEditText wsUrlInput;
    private TextInputEditText bridgeHttpUrlInput;
    private TextInputEditText tokenInput;
    private TextInputEditText adminTokenInput;
    private TextInputEditText deviceIdInput;
    private SwitchCompat autoConnectSwitch;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        if (toolbar != null) {
            setSupportActionBar(toolbar);
        }
        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
        }

        wsUrlInput = findViewById(R.id.ws_url_input);
        bridgeHttpUrlInput = findViewById(R.id.bridge_http_url_input);
        tokenInput = findViewById(R.id.token_input);
        adminTokenInput = findViewById(R.id.admin_token_input);
        deviceIdInput = findViewById(R.id.device_id_input);
        autoConnectSwitch = findViewById(R.id.auto_connect_switch);
        MaterialButton saveButton = findViewById(R.id.save_button);
        MaterialButton resetButton = findViewById(R.id.reset_button);

        loadValues();
        saveButton.setOnClickListener((view) -> saveValues());
        resetButton.setOnClickListener((view) -> {
            BridgeConfigStore.reset(this);
            loadValues();
            Toast.makeText(this, "Defaults restored", Toast.LENGTH_SHORT).show();
        });
    }

    @Override
    public boolean onSupportNavigateUp() {
        finish();
        return true;
    }

    private void loadValues() {
        wsUrlInput.setText(BridgeConfigStore.getWsUrl(this));
        bridgeHttpUrlInput.setText(BridgeConfigStore.getBridgeHttpUrl(this));
        tokenInput.setText(BridgeConfigStore.getToken(this));
        adminTokenInput.setText(BridgeConfigStore.getAdminToken(this));
        deviceIdInput.setText(BridgeConfigStore.getDeviceId(this));
        autoConnectSwitch.setChecked(BridgeConfigStore.isAutoConnectEnabled(this));
    }

    private void saveValues() {
        BridgeConfigStore.save(
                this,
                textOf(wsUrlInput),
                textOf(bridgeHttpUrlInput),
                textOf(tokenInput),
                textOf(adminTokenInput),
                textOf(deviceIdInput),
                autoConnectSwitch.isChecked()
        );
        Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show();
        finish();
    }

    private String textOf(TextInputEditText input) {
        return input.getText() == null ? "" : input.getText().toString();
    }
}
