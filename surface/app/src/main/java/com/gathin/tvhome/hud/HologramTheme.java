package com.gathin.tvhome.hud;

import android.graphics.Color;
import java.util.ArrayList;
import java.util.List;

public class HologramTheme {

    public interface OnThemeChangeListener {
        void onThemeChanged(HologramTheme newTheme);
    }

    public enum ThemeType {
        CYAN("JARVIS CYAN", 0xFF00F0FF, 0xFF00B4D8, 0x5000F0FF, 0xFF00434F),
        AMBER("CYBER AMBER", 0xFFFFB300, 0xFFFF6D00, 0x50FFB300, 0xFF543800),
        EMERALD("MATRIX GREEN", 0xFF00FF66, 0xFF00CC44, 0x5000FF66, 0xFF00471B),
        CRIMSON("SITH CRIMSON", 0xFFFF2A6D, 0xFFFF0055, 0x50FF2A6D, 0xFF5C001E),
        VIOLET("SYNTHWAVE", 0xFFB026FF, 0xFF7928CA, 0x50B026FF, 0xFF3E0066);

        public final String title;
        public final int primaryColor;
        public final int accentColor;
        public final int glowColor;
        public final int darkColor;

        ThemeType(String title, int primary, int accent, int glow, int dark) {
            this.title = title;
            this.primaryColor = primary;
            this.accentColor = accent;
            this.glowColor = glow;
            this.darkColor = dark;
        }
    }

    private static HologramTheme instance;
    private ThemeType currentType = ThemeType.CYAN;
    private final List<OnThemeChangeListener> listeners = new ArrayList<>();

    private HologramTheme() {}

    public static synchronized HologramTheme get() {
        if (instance == null) {
            instance = new HologramTheme();
        }
        return instance;
    }

    public ThemeType getThemeType() {
        return currentType;
    }

    public int getPrimary() {
        return currentType.primaryColor;
    }

    public int getAccent() {
        return currentType.accentColor;
    }

    public int getGlow() {
        return currentType.glowColor;
    }

    public int getDark() {
        return currentType.darkColor;
    }

    public void setTheme(ThemeType type) {
        if (type == null || this.currentType == type) return;
        this.currentType = type;
        for (OnThemeChangeListener l : listeners) {
            if (l != null) l.onThemeChanged(this);
        }
    }

    public void cycleNext() {
        ThemeType[] values = ThemeType.values();
        int nextIdx = (currentType.ordinal() + 1) % values.length;
        setTheme(values[nextIdx]);
    }

    public void addListener(OnThemeChangeListener listener) {
        if (listener != null && !listeners.contains(listener)) {
            listeners.add(listener);
        }
    }

    public void removeListener(OnThemeChangeListener listener) {
        listeners.remove(listener);
    }
}
