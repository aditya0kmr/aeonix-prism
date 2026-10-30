package com.gathin.tvhome.hud;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Lean, zero-dependency atmospheric weather engine using Open-Meteo.
 */
public final class WeatherEngine {
    private static final String TAG = "WeatherEngine";
    private static final long CACHE_DURATION_MS = 30 * 60 * 1000L; // 30 minutes

    public interface OnWeatherUpdatedListener {
        void onWeatherUpdated(String weatherText, int tempCelsius, String condition, String city);
    }

    private final Context context;
    private final SharedPreferences prefs;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private OnWeatherUpdatedListener listener;

    public WeatherEngine(Context context) {
        this.context = context.getApplicationContext();
        this.prefs = this.context.getSharedPreferences("aether_weather", Context.MODE_PRIVATE);
    }

    public void start(OnWeatherUpdatedListener listener) {
        this.listener = listener;

        // Deliver cached weather immediately
        String cachedText = prefs.getString("weather_text", null);
        if (cachedText != null && listener != null) {
            int temp = prefs.getInt("temp", 22);
            String cond = prefs.getString("condition", "CLEAR");
            String city = prefs.getString("city", "ONLINE");
            listener.onWeatherUpdated(cachedText, temp, cond, city);
        }

        long lastFetch = prefs.getLong("last_fetch", 0);
        long now = System.currentTimeMillis();
        if (cachedText == null || (now - lastFetch) > CACHE_DURATION_MS) {
            refresh();
        }
    }

    public void refresh() {
        executor.execute(() -> {
            try {
                // Step 1: Detect location via IP
                double lat = prefs.getFloat("lat", 28.6327f);
                double lon = prefs.getFloat("lon", 77.2198f);
                String city = prefs.getString("city", "NEW DELHI");

                try {
                    String ipResp = httpGet("http://ip-api.com/json");
                    if (ipResp != null && !ipResp.isEmpty()) {
                        JSONObject ipJson = new JSONObject(ipResp);
                        if ("success".equalsIgnoreCase(ipJson.optString("status"))) {
                            lat = ipJson.optDouble("lat", lat);
                            lon = ipJson.optDouble("lon", lon);
                            city = ipJson.optString("city", city).toUpperCase(Locale.ROOT);
                            prefs.edit()
                                    .putFloat("lat", (float) lat)
                                    .putFloat("lon", (float) lon)
                                    .putString("city", city)
                                    .apply();
                        }
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Location lookup fallback: " + e.getMessage());
                }

                // Step 2: Query Open-Meteo API
                String weatherUrl = String.format(Locale.ROOT,
                        "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                        lat, lon);

                String weatherResp = httpGet(weatherUrl);
                if (weatherResp == null || weatherResp.isEmpty()) return;

                JSONObject root = new JSONObject(weatherResp);
                JSONObject cur = root.optJSONObject("current");
                if (cur == null) return;

                double tempDouble = cur.optDouble("temperature_2m", 22.0);
                int tempCelsius = (int) Math.round(tempDouble);
                int code = cur.optInt("weather_code", 0);
                int humidity = cur.optInt("relative_humidity_2m", 50);
                double wind = cur.optDouble("wind_speed_10m", 0.0);

                String condition = wmoCodeToCondition(code);
                String weatherText = String.format(Locale.ROOT,
                        "ATMOS // %s %d°C · %s · HUM: %d%%",
                        city, tempCelsius, condition, humidity);

                // Cache
                prefs.edit()
                        .putString("weather_text", weatherText)
                        .putInt("temp", tempCelsius)
                        .putString("condition", condition)
                        .putLong("last_fetch", System.currentTimeMillis())
                        .apply();

                final String finalCity = city;
                mainHandler.post(() -> {
                    if (listener != null) {
                        listener.onWeatherUpdated(weatherText, tempCelsius, condition, finalCity);
                    }
                });

            } catch (Exception e) {
                Log.e(TAG, "Weather fetch error: " + e.getMessage());
            }
        });
    }

    private static String httpGet(String urlStr) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(6000);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Android TV; AETHER)");
            if (conn.getResponseCode() == 200) {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    return sb.toString();
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (conn != null) conn.disconnect();
        }
        return null;
    }

    private static String wmoCodeToCondition(int code) {
        switch (code) {
            case 0: return "CLEAR SKY";
            case 1: return "MAINLY CLEAR";
            case 2: return "PARTLY CLOUDY";
            case 3: return "OVERCAST";
            case 45: case 48: return "ATMOSPHERIC FOG";
            case 51: case 53: case 55: return "LIGHT DRIZZLE";
            case 61: case 63: case 65: return "RAIN SHOWER";
            case 71: case 73: case 75: return "SNOWFALL";
            case 80: case 81: case 82: return "HEAVY RAIN";
            case 95: case 96: case 99: return "ELECTRICAL STORM";
            default: return "CLEAR";
        }
    }

    public void stop() {
        this.listener = null;
    }
}
