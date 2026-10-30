package com.gathin.tvhome;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

/** The standard settings intent, or, when nothing usable answers it, the first vendor settings entry
 *  from settings_fallback_components that is installed (Xiaomi China, TCL / FFALCON, Fire OS), else the
 *  AOSP TV settings app's main screen where it is installed. */
final class SystemSettings {
    private SystemSettings() {}

    static Intent intent(Context context, String action) {
        PackageManager pm = context.getPackageManager();

        // Fire OS 7 native settings fallback integration
        Intent fireIntent = getFireOsSettingsIntent(pm, action);
        if (fireIntent != null) return fireIntent;

        Intent standard = new Intent(action);
        ResolveInfo resolved = pm.resolveActivity(standard, PackageManager.MATCH_DEFAULT_ONLY);
        // Fire OS resolves the standard actions to a CTS compliance stub that opens nothing;
        // treat it as missing so the vendor fallback runs.
        if (resolved != null && !resolved.activityInfo.name.contains("CTSDummy")) return standard;
        Intent vendor = vendorIntent(context);
        if (vendor != null) return vendor;
        // Some firmware ships the AOSP TV settings app with no filter for the standard actions (HY300 Pro+
        // projector, rk3566, Android 14): open its main screen directly. Not a vendor entry, so the Settings
        // menu's "Native settings" row stays as it was.
        Intent aosp = new Intent().setComponent(AOSP_TV_SETTINGS);
        try {
            pm.getPackageInfo(AOSP_TV_SETTINGS.getPackageName(), 0);
            return aosp;
        } catch (PackageManager.NameNotFoundException e) {
            return standard;
        }
    }

    private static Intent getFireOsSettingsIntent(PackageManager pm, String action) {
        boolean isFireDevice = (Build.MANUFACTURER != null && Build.MANUFACTURER.equalsIgnoreCase("Amazon"))
                || "sheldon".equalsIgnoreCase(Build.DEVICE)
                || "sheldon".equalsIgnoreCase(Build.PRODUCT);

        if (!isFireDevice) {
            try {
                pm.getPackageInfo("com.amazon.tv.launcher", 0);
                isFireDevice = true;
            } catch (Exception ignored) {
            }
        }
        if (!isFireDevice) return null;

        // Specialized action handling for Fire OS 7
        if (Settings.ACTION_WIFI_SETTINGS.equals(action)) {
            ComponentName wifiComponent = new ComponentName("com.amazon.tv.settings.v2", "com.amazon.tv.settings.v2.tv.network.NetworkActivity");
            try {
                pm.getActivityInfo(wifiComponent, 0);
                return new Intent().setComponent(wifiComponent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            } catch (Exception ignored) {
            }
        }
        if (Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS.equals(action)
                || Settings.ACTION_APPLICATION_SETTINGS.equals(action)) {
            ComponentName appsComponent = new ComponentName("com.amazon.tv.settings.v2", "com.amazon.tv.settings.v2.tv.applications.ApplicationsActivity");
            try {
                pm.getActivityInfo(appsComponent, 0);
                return new Intent().setComponent(appsComponent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            } catch (Exception ignored) {
            }
        }

        // Main Fire OS Settings menu fallbacks:
        // 1. com.amazon.tv.launcher/.ui.MainSettingsActivity (Native Fire TV Stick Settings Grid)
        // 2. com.amazon.tv.settings.v2/.hud.HudActivity (Fire TV Quick Settings overlay)
        // 3. com.amazon.tv.settings.v2/.tv.device.DeviceActivity (My Fire TV Settings)
        // 4. com.amazon.tv.launcher/.ui.SettingsActivity
        // 5. com.amazon.tv.settings.v2/.tv.network.NetworkActivity
        // 6. com.amazon.device.settings
        ComponentName[] fallbacks = new ComponentName[] {
            new ComponentName("com.amazon.tv.launcher", "com.amazon.tv.launcher.ui.MainSettingsActivity"),
            new ComponentName("com.amazon.tv.settings.v2", "com.amazon.tv.settings.v2.hud.HudActivity"),
            new ComponentName("com.amazon.tv.settings.v2", "com.amazon.tv.settings.v2.tv.device.DeviceActivity"),
            new ComponentName("com.amazon.tv.launcher", "com.amazon.tv.launcher.ui.SettingsActivity"),
            new ComponentName("com.amazon.tv.settings.v2", "com.amazon.tv.settings.v2.tv.network.NetworkActivity"),
            new ComponentName("com.amazon.device.settings", "com.amazon.device.settings.SettingsActivity")
        };

        for (ComponentName cn : fallbacks) {
            try {
                pm.getActivityInfo(cn, 0);
                return new Intent().setComponent(cn).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            } catch (PackageManager.NameNotFoundException ignored) {
            }
        }

        String[] firePackages = new String[] {
            "com.amazon.tv.settings.v2",
            "com.amazon.device.settings"
        };
        for (String pkg : firePackages) {
            Intent launch = pm.getLaunchIntentForPackage(pkg);
            if (launch != null) {
                return launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            }
        }

        // Try android.settings.SETTINGS directed to Amazon launcher
        Intent intent = new Intent(Settings.ACTION_SETTINGS).setPackage("com.amazon.tv.launcher");
        if (pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY) != null) {
            return intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        }

        return null;
    }

    private static final ComponentName AOSP_TV_SETTINGS =
            new ComponentName("com.android.tv.settings", "com.android.tv.settings.MainSettings");

    /** The first vendor settings entry from settings_fallback_components that is installed, or null
     *  when none is. China-market firmware keeps pages the AOSP TV settings has no row for -
     *  Xiaomi's Account & Security, where the ADB switch lives - in the vendor's own settings app;
     *  MainActivity's Settings menu offers it as "Native settings" while one is installed. */
    static Intent vendorIntent(Context context) {
        PackageManager pm = context.getPackageManager();
        for (String value : context.getResources().getStringArray(R.array.settings_fallback_components)) {
            ComponentName component = ComponentName.unflattenFromString(value);
            if (component == null) continue;
            // Explicit resolveActivity() always succeeds, so check the package exists instead.
            try {
                pm.getPackageInfo(component.getPackageName(), 0);
            } catch (PackageManager.NameNotFoundException e) {
                continue;
            }
            return new Intent().setComponent(component);
        }
        return null;
    }

    /** The TV's App info page for pkg, or null where the firmware has none (CVTE's settings app, #1202). */
    static Intent appInfo(Context context, String pkg) {
        Intent info = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + pkg));
        return context.getPackageManager().resolveActivity(info, PackageManager.MATCH_DEFAULT_ONLY) != null ? info : null;
    }
}
