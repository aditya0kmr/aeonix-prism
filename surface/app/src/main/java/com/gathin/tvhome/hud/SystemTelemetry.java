package com.gathin.tvhome.hud;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.BatteryManager;
import android.os.SystemClock;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.text.SimpleDateFormat;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class SystemTelemetry {

    public interface TelemetryListener {
        void onTelemetryUpdated();
    }

    private final Context context;
    private TelemetryListener listener;

    private int batteryLevel = 100;
    private boolean isCharging = true;
    private boolean isAcPowered = false;
    private float batteryTempC = 28.5f;
    private float batteryVoltageV = 3.9f;

    private long totalRamBytes = 0;
    private long availRamBytes = 0;
    private int ramUsagePercent = 50;

    private String wifiSsid = "OFFLINE";
    private int wifiSpeedMbps = 0;
    private String localIp = "127.0.0.1";

    private final BroadcastReceiver batteryReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context ctx, Intent intent) {
            int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            if (level >= 0 && scale > 0) {
                batteryLevel = (int) ((level / (float) scale) * 100);
            }
            int status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
            int plugged = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1);

            // If running on TV Stick or plugged directly into AC line
            if (batteryLevel <= 0 || plugged == BatteryManager.BATTERY_PLUGGED_AC || status == BatteryManager.BATTERY_STATUS_UNKNOWN) {
                isAcPowered = true;
                batteryLevel = 100;
                isCharging = false;
            } else {
                isCharging = (status == BatteryManager.BATTERY_STATUS_CHARGING ||
                        status == BatteryManager.BATTERY_STATUS_FULL);
            }

            int tempRaw = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0);
            batteryTempC = tempRaw / 10.0f;

            int voltageRaw = intent.getIntExtra(BatteryManager.EXTRA_VOLTAGE, 0);
            batteryVoltageV = voltageRaw > 1000 ? voltageRaw / 1000.0f : voltageRaw;

            refreshMemory();
            refreshNetwork();
            if (listener != null) listener.onTelemetryUpdated();
        }
    };

    public SystemTelemetry(Context context) {
        this.context = context.getApplicationContext();
    }

    public void start(TelemetryListener listener) {
        this.listener = listener;
        IntentFilter filter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        context.registerReceiver(batteryReceiver, filter);
        refreshMemory();
        refreshNetwork();
    }

    public void stop() {
        try {
            context.unregisterReceiver(batteryReceiver);
        } catch (Exception ignored) {}
        this.listener = null;
    }

    public void refreshMemory() {
        try {
            ActivityManager actManager = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
            ActivityManager.MemoryInfo memInfo = new ActivityManager.MemoryInfo();
            if (actManager != null) {
                actManager.getMemoryInfo(memInfo);
                totalRamBytes = memInfo.totalMem;
                availRamBytes = memInfo.availMem;
                long used = totalRamBytes - availRamBytes;
                ramUsagePercent = (int) (((double) used / totalRamBytes) * 100.0);
            }
        } catch (Exception ignored) {}
    }

    public void refreshNetwork() {
        try {
            WifiManager wifiManager = (WifiManager) context.getSystemService(Context.WIFI_SERVICE);
            if (wifiManager != null && wifiManager.isWifiEnabled()) {
                WifiInfo info = wifiManager.getConnectionInfo();
                if (info != null && info.getNetworkId() != -1) {
                    String ssid = info.getSSID();
                    if (ssid != null && ssid.startsWith("\"") && ssid.endsWith("\"")) {
                        ssid = ssid.substring(1, ssid.length() - 1);
                    }
                    wifiSsid = (ssid == null || ssid.equals("<unknown ssid>")) ? "NET_ONLINE" : ssid;
                    wifiSpeedMbps = info.getLinkSpeed();
                } else {
                    wifiSsid = "CELLULAR";
                    wifiSpeedMbps = 0;
                }
            } else {
                wifiSsid = "OFFLINE";
                wifiSpeedMbps = 0;
            }
            localIp = getLocalIpAddress();
        } catch (Exception ignored) {}
    }

    private String getLocalIpAddress() {
        try {
            List<NetworkInterface> interfaces = Collections.list(NetworkInterface.getNetworkInterfaces());
            for (NetworkInterface intf : interfaces) {
                List<InetAddress> addrs = Collections.list(intf.getInetAddresses());
                for (InetAddress addr : addrs) {
                    if (!addr.isLoopbackAddress()) {
                        String sAddr = addr.getHostAddress();
                        if (sAddr != null && sAddr.indexOf(':') < 0) {
                            return sAddr;
                        }
                    }
                }
            }
        } catch (Exception ignored) {}
        return "127.0.0.1";
    }

    public int getBatteryLevel() { return batteryLevel; }
    public boolean isCharging() { return isCharging; }
    public boolean isAcPowered() { return isAcPowered; }
    public float getBatteryTempC() { return batteryTempC; }
    public float getBatteryVoltageV() { return batteryVoltageV; }
    public int getRamUsagePercent() { return ramUsagePercent; }
    public long getTotalRamBytes() { return totalRamBytes; }
    public long getAvailRamBytes() { return availRamBytes; }
    public String getWifiSsid() { return wifiSsid; }
    public int getWifiSpeedMbps() { return wifiSpeedMbps; }
    public String getLocalIp() { return localIp; }

    public String getStardateString() {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy.DDD", Locale.US);
        long uptimeHours = SystemClock.elapsedRealtime() / (1000 * 60 * 60);
        return "STARDATE // " + sdf.format(new Date()) + " :: T+" + uptimeHours + "H";
    }
}
