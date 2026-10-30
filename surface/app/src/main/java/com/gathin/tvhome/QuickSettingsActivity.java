package com.gathin.tvhome;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

/**
 * The panel the remote's Settings button opens when {@code settings_key_panel} is on (HomeKeyService):
 * a few glass rows under the Settings pill, over Home or whatever app is playing. Translucent and in a
 * task of its own, so the app behind keeps running and Back returns to it. Pressing Settings again
 * closes the panel.
 */
public final class QuickSettingsActivity extends Activity {
    @Override
    protected void attachBaseContext(android.content.Context base) {
        super.attachBaseContext(LauncherLocale.wrap(base));   // locale
    }


    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_quick_settings);
        if (getResources().getBoolean(R.bool.rtl_menu_bar)) {
            View panel = findViewById(R.id.panel);
            android.widget.FrameLayout.LayoutParams position =
                    (android.widget.FrameLayout.LayoutParams) panel.getLayoutParams();
            position.gravity = android.view.Gravity.TOP | android.view.Gravity.LEFT;
            int inset = position.getMarginEnd();
            position.setMarginEnd(0);
            position.setMargins(inset, position.topMargin, 0, position.bottomMargin);
            panel.setLayoutParams(position);
        }
        findViewById(R.id.scrim).setOnClickListener(v -> finish());
        LinearLayout rows = findViewById(R.id.rows);

        // 1. ⚡ Turbo Clean RAM
        addActionRow(rows, R.drawable.ic_apps, "⚡ Turbo Clean RAM", "Free Memory & Cache", () -> {
            long before = getFreeMemoryMb();
            ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
            if (am != null) {
                List<ActivityManager.RunningAppProcessInfo> procs = am.getRunningAppProcesses();
                if (procs != null) {
                    for (ActivityManager.RunningAppProcessInfo p : procs) {
                        if (p.pkgList != null) {
                            for (String pkg : p.pkgList) {
                                if (!pkg.equals(getPackageName()) && !pkg.contains("amazon.tv.launcher")) {
                                    am.killBackgroundProcesses(pkg);
                                }
                            }
                        }
                    }
                }
            }
            System.gc();
            long after = getFreeMemoryMb();
            long freed = Math.max(0, after - before);
            Toast.makeText(this, "⚡ Turbo Clean: " + (freed > 0 ? (freed + " MB RAM Freed") : "Memory Optimized"), Toast.LENGTH_SHORT).show();
        });

        // 2. 💤 Sleep Display / Standby
        addActionRow(rows, R.drawable.ic_home_settings, "💤 Sleep Display", "Standby Mode", () -> {
            startActivity(new Intent(this, ClockActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        });

        // 3. 🚀 Stock Fire TV Home
        addActionRow(rows, R.drawable.ic_home_settings, "🚀 Stock Fire TV Home", "15s Bypass Mode", () -> {
            HomeKeyService.bypassAndLaunchStockHome(this);
        });

        // 4. 🔄 Restart Fire TV Stick
        addActionRow(rows, R.drawable.ic_settings, "🔄 Restart Fire TV", "Reboot System", () -> {
            HomeKeyService.openPowerMenu();
        });

        addDivider(rows);

        addRow(rows, R.drawable.ic_settings, R.string.tv_settings, 0, SystemSettings.intent(this, Settings.ACTION_SETTINGS));
        addRow(rows, R.drawable.ic_picture, R.string.quick_picture, 0, SystemSettings.intent(this, Settings.ACTION_DISPLAY_SETTINGS));
        addRow(rows, R.drawable.ic_wifi, R.string.quick_network, 0, SystemSettings.intent(this, Settings.ACTION_WIFI_SETTINGS));
        addRow(rows, R.drawable.ic_apps, R.string.quick_apps, R.string.quick_apps_hint,
                SystemSettings.intent(this, Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS));
        // Through Home, so it rebuilds with the new choices when Launcher settings closes.
        addRow(rows, R.drawable.ic_home_settings, R.string.launcher_settings, 0,
                new Intent(this, MainActivity.class).setAction(MainActivity.ACTION_LAUNCHER_SETTINGS));
        rows.getChildAt(0).requestFocus();
    }

    /** Settings pressed again while the panel is up. */
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        finish();
    }

    /** Anything else taking the screen (Home, an app, a screensaver) closes the panel. */
    @Override
    protected void onPause() {
        super.onPause();
        finish();
        overridePendingTransition(0, 0);
    }

    private void addDivider(LinearLayout rows) {
        View div = new View(this);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 1);
        int margin = (int) (12 * getResources().getDisplayMetrics().density);
        int vert = (int) (4 * getResources().getDisplayMetrics().density);
        lp.setMargins(margin, vert, margin, vert);
        div.setLayoutParams(lp);
        div.setBackgroundColor(0x33FFFFFF);
        rows.addView(div);
    }

    private void addActionRow(LinearLayout rows, int icon, String title, String hint, Runnable action) {
        View row = getLayoutInflater().inflate(R.layout.item_input, rows, false);
        ((ImageView) row.findViewById(R.id.icon)).setImageResource(icon);
        ((TextView) row.findViewById(R.id.title)).setText(title);
        row.findViewById(R.id.dot).setVisibility(View.GONE);
        TextView hintView = row.findViewById(R.id.status);
        if (hint != null && !hint.isEmpty()) hintView.setText(hint);
        else hintView.setVisibility(View.GONE);
        row.setOnClickListener(v -> {
            try {
                action.run();
            } catch (Exception e) {
                Toast.makeText(this, R.string.not_available, Toast.LENGTH_SHORT).show();
            }
            finish();
        });
        rows.addView(row);
    }

    private long getFreeMemoryMb() {
        ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return 0;
        ActivityManager.MemoryInfo mi = new ActivityManager.MemoryInfo();
        am.getMemoryInfo(mi);
        return mi.availMem / (1024 * 1024);
    }

    private void addRow(LinearLayout rows, int icon, int title, int status, Intent target) {
        View row = getLayoutInflater().inflate(R.layout.item_input, rows, false);
        ((ImageView) row.findViewById(R.id.icon)).setImageResource(icon);
        ((TextView) row.findViewById(R.id.title)).setText(title);
        row.findViewById(R.id.dot).setVisibility(View.GONE);
        TextView hint = row.findViewById(R.id.status);
        if (status != 0) hint.setText(status);
        else hint.setVisibility(View.GONE);
        row.setOnClickListener(v -> {
            try {
                startActivity(target.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (ActivityNotFoundException | SecurityException e) {
                Toast.makeText(this, R.string.not_available, Toast.LENGTH_SHORT).show();
            }
            finish();
        });
        rows.addView(row);
    }
}
