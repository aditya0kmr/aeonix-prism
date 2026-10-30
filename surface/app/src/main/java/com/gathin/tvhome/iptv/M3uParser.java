package com.gathin.tvhome.iptv;

import android.content.Context;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Fast, lean M3U / M3U8 playlist parser for IPTV live streams.
 */
public final class M3uParser {
    private static final String TAG = "M3uParser";

    private static final Pattern TVG_ID_PATTERN = Pattern.compile("tvg-id=\"([^\"]*)\"");
    private static final Pattern TVG_NAME_PATTERN = Pattern.compile("tvg-name=\"([^\"]*)\"");
    private static final Pattern TVG_LOGO_PATTERN = Pattern.compile("tvg-logo=\"([^\"]*)\"");
    private static final Pattern GROUP_TITLE_PATTERN = Pattern.compile("group-title=\"([^\"]*)\"");
    private static final Pattern TVG_COUNTRY_PATTERN = Pattern.compile("tvg-country=\"([^\"]*)\"");

    private M3uParser() {}

    /**
     * Loads channels either from custom external files on storage or built-in assets.
     */
    public static List<Channel> loadChannels(Context context) {
        // Priority 1: App external files dir iptv.m3u
        File appM3u = new File(context.getExternalFilesDir(null), "iptv.m3u");
        if (appM3u.exists() && appM3u.length() > 0) {
            try (InputStream in = new FileInputStream(appM3u)) {
                Log.i(TAG, "Loading IPTV playlist from: " + appM3u.getAbsolutePath());
                return parse(in);
            } catch (Exception e) {
                Log.w(TAG, "Failed to read app external iptv.m3u: " + e.getMessage());
            }
        }

        // Priority 2: Root sdcard /sdcard/iptv.m3u
        File sdcardM3u = new File("/sdcard/iptv.m3u");
        if (sdcardM3u.exists() && sdcardM3u.length() > 0) {
            try (InputStream in = new FileInputStream(sdcardM3u)) {
                Log.i(TAG, "Loading IPTV playlist from: " + sdcardM3u.getAbsolutePath());
                return parse(in);
            } catch (Exception e) {
                Log.w(TAG, "Failed to read /sdcard/iptv.m3u: " + e.getMessage());
            }
        }

        // Priority 3: Built-in assets
        try (InputStream in = context.getAssets().open("iptv/world_channels.m3u")) {
            Log.i(TAG, "Loading built-in IPTV playlist from assets");
            return parse(in);
        } catch (Exception e) {
            Log.e(TAG, "Failed to load built-in world_channels.m3u: " + e.getMessage());
            return new ArrayList<>();
        }
    }

    /**
     * Parses an M3U input stream line by line.
     */
    public static List<Channel> parse(InputStream in) {
        List<Channel> channels = new ArrayList<>(200);
        if (in == null) return channels;

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            String curId = "";
            String curName = "";
            String curCat = "GENERAL";
            String curCountry = "";
            String curLogo = "";

            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;

                if (line.startsWith("#EXTINF:")) {
                    // Extract attributes
                    curId = extractPattern(TVG_ID_PATTERN, line, "");
                    curName = extractPattern(TVG_NAME_PATTERN, line, "");
                    curCat = extractPattern(GROUP_TITLE_PATTERN, line, "GENERAL");
                    curCountry = extractPattern(TVG_COUNTRY_PATTERN, line, "");
                    curLogo = extractPattern(TVG_LOGO_PATTERN, line, "");

                    // The display name is after the last comma
                    int lastComma = line.lastIndexOf(',');
                    if (lastComma != -1 && lastComma < line.length() - 1) {
                        String titleAfterComma = line.substring(lastComma + 1).trim();
                        if (!titleAfterComma.isEmpty()) {
                            curName = titleAfterComma;
                        }
                    }

                    // Fallback name
                    if (curName.isEmpty()) {
                        curName = curId.isEmpty() ? "Channel " + (channels.size() + 1) : curId;
                    }

                    // Normalize category
                    curCat = normalizeCategory(curCat);

                } else if (!line.startsWith("#")) {
                    // This is the stream URL
                    if (line.startsWith("http://") || line.startsWith("https://")) {
                        Channel channel = new Channel(curId, curName, curCat, curCountry, curLogo, line);
                        channels.add(channel);
                    }
                    // Reset transient fields
                    curId = "";
                    curName = "";
                    curCat = "GENERAL";
                    curCountry = "";
                    curLogo = "";
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error parsing M3U: " + e.getMessage(), e);
        }

        return channels;
    }

    private static String extractPattern(Pattern pattern, String text, String defaultValue) {
        Matcher m = pattern.matcher(text);
        if (m.find() && m.groupCount() >= 1) {
            String val = m.group(1);
            if (val != null && !val.trim().isEmpty()) {
                return val.trim();
            }
        }
        return defaultValue;
    }

    public static String normalizeCategory(String raw) {
        if (raw == null) return "GENERAL";
        String lower = raw.trim().toLowerCase(Locale.ROOT);
        if (lower.contains("news") || lower.contains("weather")) return "NEWS";
        if (lower.contains("movie") || lower.contains("cinema") || lower.contains("film") || lower.contains("series")) return "MOVIES";
        if (lower.contains("sport") || lower.contains("racing") || lower.contains("outdoor")) return "SPORTS";
        if (lower.contains("music") || lower.contains("song") || lower.contains("radio")) return "MUSIC";
        if (lower.contains("tech") || lower.contains("science") || lower.contains("space") || lower.contains("education")) return "TECH & SCIENCE";
        if (lower.contains("anim") || lower.contains("kid") || lower.contains("cartoon")) return "ANIMATION";
        if (lower.contains("doc") || lower.contains("nature") || lower.contains("history") || lower.contains("travel")) return "DOCUMENTARY";
        return raw.toUpperCase(Locale.ROOT);
    }

    public static Map<String, List<Channel>> groupByCategory(List<Channel> channels) {
        Map<String, List<Channel>> map = new LinkedHashMap<>();
        map.put("ALL", new ArrayList<>(channels));

        for (Channel c : channels) {
            String cat = c.getCategory();
            List<Channel> list = map.computeIfAbsent(cat, k -> new ArrayList<>());
            list.add(c);
        }
        return map;
    }

    /**
     * Downloads an M3U playlist from a remote URL and caches it in the app's external files dir.
     */
    public static boolean savePlaylistFromUrl(Context context, String urlString) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlString);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(15000);
            conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Android TV; AETHER)");
            if (conn.getResponseCode() == 200) {
                File target = new File(context.getExternalFilesDir(null), "iptv.m3u");
                try (InputStream in = conn.getInputStream();
                     FileOutputStream out = new FileOutputStream(target)) {
                    byte[] buffer = new byte[8192];
                    int bytesRead;
                    while ((bytesRead = in.read(buffer)) != -1) {
                        out.write(buffer, 0, bytesRead);
                    }
                    out.flush();
                }
                return true;
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to download M3U: " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
        return false;
    }

    /**
     * Deletes the custom M3U playlist file so the player falls back to built-in assets.
     */
    public static boolean restoreDefaultPlaylist(Context context) {
        File target = new File(context.getExternalFilesDir(null), "iptv.m3u");
        if (target.exists()) {
            return target.delete();
        }
        return true;
    }
}
