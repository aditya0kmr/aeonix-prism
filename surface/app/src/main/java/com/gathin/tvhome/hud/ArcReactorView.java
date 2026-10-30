package com.gathin.tvhome.hud;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.DashPathEffect;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.SweepGradient;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.LinearInterpolator;
import com.gathin.tvhome.audio.CyberSoundSynth;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class ArcReactorView extends View {

    public interface OnCoreClickListener {
        void onCoreClicked();
    }

    private OnCoreClickListener coreClickListener;
    private final HologramTheme theme = HologramTheme.get();
    private SystemTelemetry telemetry;

    // Paints
    private final Paint gridPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ringOuterPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ringMiddlePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint batteryArcPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ramArcPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint corePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textClockPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textSubPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint visualizerPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    // Dynamic rotation angles
    private float outerRingAngle = 0f;
    private float middleRingAngle = 0f;
    private float innerRingAngle = 0f;
    private float pulseAlpha = 0.5f;
    private float chargingSparkProgress = 0f;

    // Gyro Parallax Offsets
    private float parallaxPitch = 0f;
    private float parallaxRoll = 0f;

    // Audio Visualizer data (36 frequency bins around the circle)
    private static final int VISUALIZER_BINS = 36;
    private final float[] visualizerHeights = new float[VISUALIZER_BINS];
    private final float[] visualizerTargets = new float[VISUALIZER_BINS];

    private final RectF batteryRect = new RectF();
    private final RectF ramRect = new RectF();
    private final RectF outerRingRect = new RectF();
    private final Path tempPath = new Path();

    private final SimpleDateFormat clockFormat = new SimpleDateFormat("HH:mm:ss", Locale.US);
    private ValueAnimator loopAnimator;

    public ArcReactorView(Context context) {
        super(context);
        init();
    }

    public ArcReactorView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        setLayerType(View.LAYER_TYPE_HARDWARE, null);

        // Configure Paints
        gridPaint.setColor(0x1800F0FF);
        gridPaint.setStrokeWidth(1.5f);
        gridPaint.setStyle(Paint.Style.STROKE);

        ringOuterPaint.setStyle(Paint.Style.STROKE);
        ringOuterPaint.setStrokeWidth(2.5f);

        ringMiddlePaint.setStyle(Paint.Style.STROKE);
        ringMiddlePaint.setStrokeWidth(4f);
        ringMiddlePaint.setPathEffect(new DashPathEffect(new float[]{18f, 10f, 6f, 10f}, 0f));

        batteryArcPaint.setStyle(Paint.Style.STROKE);
        batteryArcPaint.setStrokeWidth(8f);
        batteryArcPaint.setStrokeCap(Paint.Cap.ROUND);

        ramArcPaint.setStyle(Paint.Style.STROKE);
        ramArcPaint.setStrokeWidth(4.5f);
        ramArcPaint.setStrokeCap(Paint.Cap.ROUND);

        corePaint.setStyle(Paint.Style.FILL);

        glowPaint.setStyle(Paint.Style.FILL);

        textClockPaint.setTextAlign(Paint.Align.CENTER);
        textClockPaint.setFakeBoldText(true);

        textSubPaint.setTextAlign(Paint.Align.CENTER);
        textSubPaint.setTextSize(26f);

        visualizerPaint.setStyle(Paint.Style.STROKE);
        visualizerPaint.setStrokeCap(Paint.Cap.ROUND);
        visualizerPaint.setStrokeWidth(3.5f);

        updateThemePaints();
        theme.addListener(t -> post(this::updateThemePaints));

        startContinuousAnimation();
    }

    private void updateThemePaints() {
        int primary = theme.getPrimary();
        int accent = theme.getAccent();
        int glow = theme.getGlow();
        int dark = theme.getDark();

        gridPaint.setColor((primary & 0x00FFFFFF) | 0x1A000000);
        ringOuterPaint.setColor(accent);
        ringMiddlePaint.setColor(primary);
        batteryArcPaint.setColor(primary);
        ramArcPaint.setColor(accent);
        corePaint.setColor(primary);
        glowPaint.setColor(glow);
        textClockPaint.setColor(0xFFF0F8FF);
        textSubPaint.setColor(primary);
        visualizerPaint.setColor(primary);
        invalidate();
    }

    public void setTelemetry(SystemTelemetry telemetry) {
        this.telemetry = telemetry;
        invalidate();
    }

    public void setParallax(float pitch, float roll) {
        this.parallaxPitch = pitch;
        this.parallaxRoll = roll;
        invalidate();
    }

    public void setOnCoreClickListener(OnCoreClickListener listener) {
        this.coreClickListener = listener;
    }

    private void startContinuousAnimation() {
        loopAnimator = ValueAnimator.ofFloat(0f, 1f);
        loopAnimator.setDuration(1000);
        loopAnimator.setRepeatCount(ValueAnimator.INFINITE);
        loopAnimator.setInterpolator(new LinearInterpolator());
        loopAnimator.addUpdateListener(animation -> {
            long now = SystemClock.uptimeMillis();

            // Continuous rotation rates
            outerRingAngle = (now / 45.0f) % 360f;
            middleRingAngle = -(now / 28.0f) % 360f;
            innerRingAngle = (now / 15.0f) % 360f;

            // Breathing pulse effect
            pulseAlpha = 0.35f + 0.35f * (float) Math.sin(now / 350.0);

            // Charging spark progression
            chargingSparkProgress = (now % 1200L) / 1200.0f;

            // Simulate reactive audio wave movement for visualizer
            simulateAudioVisualizer(now);

            invalidate();
        });
        loopAnimator.start();
    }

    private void simulateAudioVisualizer(long now) {
        for (int i = 0; i < VISUALIZER_BINS; i++) {
            double freq1 = Math.sin((now / 180.0) + (i * 0.45));
            double freq2 = Math.cos((now / 110.0) - (i * 0.3));
            float target = (float) Math.max(4.0, (freq1 * freq2 * 32.0) + 18.0);
            visualizerTargets[i] = target;
            visualizerHeights[i] += (visualizerTargets[i] - visualizerHeights[i]) * 0.25f;
        }
    }

    public void pauseAnimation() {
        if (loopAnimator != null && loopAnimator.isRunning()) {
            loopAnimator.pause();
        }
    }

    public void resumeAnimation() {
        if (loopAnimator != null && loopAnimator.isPaused()) {
            loopAnimator.resume();
        } else if (loopAnimator == null || !loopAnimator.isRunning()) {
            startContinuousAnimation();
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        if (loopAnimator != null) {
            loopAnimator.cancel();
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        int w = getWidth();
        int h = getHeight();
        if (w <= 0 || h <= 0) return;

        float cx = w / 2.0f;
        float cy = h / 2.0f;
        float maxRadius = Math.min(w, h) * (w > h ? 0.35f : 0.44f);

        // Draw Ambient Cyber Grid with Gyro Tilt
        drawCyberGrid(canvas, w, h);

        // Apply 3D parallax offset to the Arc Reactor Core
        canvas.save();
        float coreShiftX = parallaxRoll * 42.0f;
        float coreShiftY = parallaxPitch * 42.0f;
        canvas.translate(coreShiftX, coreShiftY);

        // 1. Draw Audio Visualizer Equalizer Ring
        drawCircularVisualizer(canvas, cx, cy, maxRadius * 0.96f);

        // 2. Draw Outer Kinetic Octagon / Tactical Ring
        drawOuterTacticalRing(canvas, cx, cy, maxRadius * 0.85f);

        // 3. Draw Middle Counter-Rotating Telemetry Ring
        drawMiddleTelemetryRing(canvas, cx, cy, maxRadius * 0.70f);

        // 4. Draw Battery Energy Arc & Ram Gauge Arc
        drawBatteryAndRamArcs(canvas, cx, cy, maxRadius * 0.56f);

        // 5. Draw Inner Glowing Reactor Core
        drawInnerReactorCore(canvas, cx, cy, maxRadius * 0.32f);

        // 6. Draw Chronometer & Stardate Text
        drawChronometer(canvas, cx, cy, maxRadius * 0.30f);

        canvas.restore();
    }

    private void drawCyberGrid(Canvas canvas, int w, int h) {
        float gridShiftX = parallaxRoll * 12.0f;
        float gridShiftY = parallaxPitch * 12.0f;

        canvas.save();
        canvas.translate(gridShiftX, gridShiftY);

        float step = 72f;
        for (float x = 0; x <= w; x += step) {
            canvas.drawLine(x, 0, x, h, gridPaint);
        }
        for (float y = 0; y <= h; y += step) {
            canvas.drawLine(0, y, w, y, gridPaint);
        }

        // Crosshairs
        float cross = 24f;
        canvas.drawLine(w / 2f - cross, h / 2f, w / 2f + cross, h / 2f, ringOuterPaint);
        canvas.drawLine(w / 2f, h / 2f - cross, w / 2f, h / 2f + cross, ringOuterPaint);

        canvas.restore();
    }

    private void drawCircularVisualizer(Canvas canvas, float cx, float cy, float radius) {
        float angleStep = 360f / VISUALIZER_BINS;
        for (int i = 0; i < VISUALIZER_BINS; i++) {
            float angle = (float) Math.toRadians(i * angleStep + outerRingAngle * 0.5f);
            float barLen = visualizerHeights[i];
            float x1 = cx + (float) Math.cos(angle) * radius;
            float y1 = cy + (float) Math.sin(angle) * radius;
            float x2 = cx + (float) Math.cos(angle) * (radius + barLen);
            float y2 = cy + (float) Math.sin(angle) * (radius + barLen);
            canvas.drawLine(x1, y1, x2, y2, visualizerPaint);
        }
    }

    private void drawOuterTacticalRing(Canvas canvas, float cx, float cy, float radius) {
        canvas.save();
        canvas.rotate(outerRingAngle, cx, cy);

        outerRingRect.set(cx - radius, cy - radius, cx + radius, cy + radius);
        canvas.drawCircle(cx, cy, radius, ringOuterPaint);

        // 8 Tactical Corner Notches
        for (int i = 0; i < 8; i++) {
            float angle = (float) Math.toRadians(i * 45f);
            float px1 = cx + (float) Math.cos(angle) * (radius - 12f);
            float py1 = cy + (float) Math.sin(angle) * (radius - 12f);
            float px2 = cx + (float) Math.cos(angle) * (radius + 12f);
            float py2 = cy + (float) Math.sin(angle) * (radius + 12f);
            canvas.drawLine(px1, py1, px2, py2, ringOuterPaint);
        }
        canvas.restore();
    }

    private void drawMiddleTelemetryRing(Canvas canvas, float cx, float cy, float radius) {
        canvas.save();
        canvas.rotate(middleRingAngle, cx, cy);
        canvas.drawCircle(cx, cy, radius, ringMiddlePaint);
        canvas.restore();
    }

    private void drawBatteryAndRamArcs(Canvas canvas, float cx, float cy, float radius) {
        int batteryLvl = telemetry != null ? telemetry.getBatteryLevel() : 75;
        int ramPercent = telemetry != null ? telemetry.getRamUsagePercent() : 48;
        boolean isCharging = telemetry != null && telemetry.isCharging();

        // Battery Arc (outer arc: 240 degrees sweep from 150 deg)
        float startAngle = 150f;
        float totalSweep = 240f;
        float batSweep = totalSweep * (batteryLvl / 100.0f);

        batteryRect.set(cx - radius, cy - radius, cx + radius, cy + radius);

        // Background track (dim)
        batteryArcPaint.setColor(theme.getDark());
        canvas.drawArc(batteryRect, startAngle, totalSweep, false, batteryArcPaint);

        // Active Battery Arc
        batteryArcPaint.setColor(isCharging ? 0xFF00FF66 : theme.getPrimary());
        canvas.drawArc(batteryRect, startAngle, batSweep, false, batteryArcPaint);

        // Spark pulse when charging
        if (isCharging) {
            float sparkAngle = startAngle + (batSweep * chargingSparkProgress);
            float rad = (float) Math.toRadians(sparkAngle);
            float sx = cx + (float) Math.cos(rad) * radius;
            float sy = cy + (float) Math.sin(rad) * radius;
            glowPaint.setColor(0xFFF0F8FF);
            canvas.drawCircle(sx, sy, 7f, glowPaint);
        }

        // RAM Arc (inner arc: 180 degrees sweep)
        float ramRadius = radius - 18f;
        ramRect.set(cx - ramRadius, cy - ramRadius, cx + ramRadius, cy + ramRadius);
        ramArcPaint.setColor(theme.getDark());
        canvas.drawArc(ramRect, 180f, 180f, false, ramArcPaint);

        ramArcPaint.setColor(theme.getAccent());
        canvas.drawArc(ramRect, 180f, 180f * (ramPercent / 100f), false, ramArcPaint);
    }

    private void drawInnerReactorCore(Canvas canvas, float cx, float cy, float radius) {
        // Core breathing glow
        int glowAlpha = (int) (pulseAlpha * 255);
        glowPaint.setColor((theme.getGlow() & 0x00FFFFFF) | (glowAlpha << 24));
        canvas.drawCircle(cx, cy, radius * 1.25f, glowPaint);

        // Outer Core Hexagon
        canvas.save();
        canvas.rotate(innerRingAngle, cx, cy);
        tempPath.reset();
        for (int i = 0; i < 6; i++) {
            float a = (float) Math.toRadians(i * 60f);
            float x = cx + (float) Math.cos(a) * radius;
            float y = cy + (float) Math.sin(a) * radius;
            if (i == 0) tempPath.moveTo(x, y);
            else tempPath.lineTo(x, y);
        }
        tempPath.close();
        ringOuterPaint.setStrokeWidth(2f);
        canvas.drawPath(tempPath, ringOuterPaint);
        canvas.restore();
    }

    private void drawChronometer(Canvas canvas, float cx, float cy, float radius) {
        long now = System.currentTimeMillis();
        String timeStr = clockFormat.format(new Date(now));

        // Clean, stable clock without restless millisecond jitter
        textClockPaint.setColor(0xFFFFFFFF);
        textClockPaint.setTextSize(radius * 0.48f);
        canvas.drawText(timeStr, cx, cy + (textClockPaint.getTextSize() * 0.35f), textClockPaint);

        // Top Status (Restrained System State)
        textSubPaint.setColor(theme.getPrimary());
        textSubPaint.setTextSize(radius * 0.18f);
        canvas.drawText("SYSTEM OPTIMAL", cx, cy - (radius * 0.45f), textSubPaint);

        // Bottom Stardate
        String dateStr = telemetry != null ? telemetry.getStardateString() : "STARDATE 2026.302";
        textSubPaint.setColor(0xCCFFFFFF);
        canvas.drawText(dateStr, cx, cy + (radius * 0.70f), textSubPaint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (event.getAction() == MotionEvent.ACTION_UP) {
            float dx = event.getX() - (getWidth() / 2f);
            float dy = event.getY() - (getHeight() / 2f);
            float dist = (float) Math.sqrt(dx * dx + dy * dy);
            float coreRadius = Math.min(getWidth(), getHeight()) * 0.32f;

            if (dist <= coreRadius) {
                CyberSoundSynth.get().playChirp();
                if (coreClickListener != null) {
                    coreClickListener.onCoreClicked();
                }
                return true;
            }
        }
        return true;
    }
}
