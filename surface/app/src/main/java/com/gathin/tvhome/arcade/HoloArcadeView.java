package com.gathin.tvhome.arcade;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.LinearInterpolator;
import com.gathin.tvhome.audio.CyberSoundSynth;
import com.gathin.tvhome.hud.HologramTheme;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class HoloArcadeView extends View {

    public interface OnExitListener {
        void onExit();
    }

    public enum GameMode {
        VECTOR_DODGE,
        CYBER_HACK
    }

    private GameMode currentMode = GameMode.VECTOR_DODGE;
    private OnExitListener exitListener;

    private final Paint shipPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hazardPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint gridPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint nodePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint cursorPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    // VectorDodge state
    private float shipX = 0f;
    private float shipY = 0f;
    private float shipTargetX = 0f;
    private int dodgeScore = 0;
    private boolean isGameOver = false;

    private static class Hazard {
        float x, y, size, speed;
        Hazard(float x, float y, float size, float speed) {
            this.x = x; this.y = y; this.size = size; this.speed = speed;
        }
    }
    private final List<Hazard> hazards = new ArrayList<>();
    private final Random random = new Random();

    // CyberHack state
    private static final int HACK_GRID = 4;
    private final int[] hackSequence = new int[8];
    private final List<Integer> playerInput = new ArrayList<>();
    private int hackLevel = 1;
    private long hackTimerEnd = 0;
    private boolean hackRevealing = true;
    private long hackRevealStart = 0;

    // D-Pad Cursor navigation for CyberHack
    private int hackCursorRow = 0;
    private int hackCursorCol = 0;

    private ValueAnimator gameLoop;
    private final Path shipPath = new Path();

    public HoloArcadeView(Context context) {
        super(context);
        init();
    }

    public HoloArcadeView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        setLayerType(View.LAYER_TYPE_HARDWARE, null);
        setFocusable(true);
        setFocusableInTouchMode(true);

        shipPaint.setStyle(Paint.Style.STROKE);
        shipPaint.setStrokeWidth(3f);

        hazardPaint.setStyle(Paint.Style.FILL);

        textPaint.setTextAlign(Paint.Align.CENTER);
        textPaint.setFakeBoldText(true);

        gridPaint.setStyle(Paint.Style.STROKE);
        gridPaint.setStrokeWidth(1.2f);

        nodePaint.setStyle(Paint.Style.FILL_AND_STROKE);

        cursorPaint.setStyle(Paint.Style.STROKE);
        cursorPaint.setStrokeWidth(3.5f);
        cursorPaint.setColor(0xFF00F0FF);

        updateThemePaints();
        HologramTheme.get().addListener(t -> post(this::updateThemePaints));

        startGameLoop();
    }

    private void updateThemePaints() {
        int primary = HologramTheme.get().getPrimary();
        int accent = HologramTheme.get().getAccent();

        shipPaint.setColor(primary);
        hazardPaint.setColor(0xFFFF2A6D);
        textPaint.setColor(0xFFF0F8FF);
        gridPaint.setColor((primary & 0x00FFFFFF) | 0x22000000);
        nodePaint.setColor(accent);
        cursorPaint.setColor(primary);
        invalidate();
    }

    public void setGameMode(GameMode mode) {
        this.currentMode = mode;
        resetGame();
    }

    public void setOnExitListener(OnExitListener listener) {
        this.exitListener = listener;
    }

    public void applyGyroInput(float roll) {
        if (currentMode == GameMode.VECTOR_DODGE && !isGameOver) {
            shipTargetX = (getWidth() / 2f) + (roll * (getWidth() * 0.42f));
        }
    }

    public void resetGame() {
        isGameOver = false;
        dodgeScore = 0;
        hazards.clear();
        shipX = getWidth() > 0 ? getWidth() / 2f : 960f;
        shipY = getHeight() > 0 ? getHeight() * 0.82f : 880f;
        shipTargetX = shipX;

        if (currentMode == GameMode.CYBER_HACK) {
            hackLevel = 1;
            hackCursorRow = 0;
            hackCursorCol = 0;
            startNewHackRound();
        }
    }

    private void startNewHackRound() {
        playerInput.clear();
        int seqLen = Math.min(3 + hackLevel, 8);
        for (int i = 0; i < seqLen; i++) {
            hackSequence[i] = random.nextInt(HACK_GRID * HACK_GRID);
        }
        hackRevealing = true;
        hackRevealStart = System.currentTimeMillis();
        hackTimerEnd = hackRevealStart + 2500 + (hackLevel * 3000);
    }

    private void startGameLoop() {
        gameLoop = ValueAnimator.ofFloat(0f, 1f);
        gameLoop.setDuration(1000);
        gameLoop.setRepeatCount(ValueAnimator.INFINITE);
        gameLoop.setInterpolator(new LinearInterpolator());
        gameLoop.addUpdateListener(anim -> {
            if (currentMode == GameMode.VECTOR_DODGE) {
                updateVectorDodge();
            } else {
                updateCyberHack();
            }
            invalidate();
        });
        gameLoop.start();
    }

    private void updateVectorDodge() {
        if (isGameOver || getWidth() <= 0) return;

        // Smooth ship positioning
        shipX += (shipTargetX - shipX) * 0.22f;
        shipY = getHeight() * 0.82f;

        // Spawn hazards
        if (random.nextFloat() < 0.05f + (dodgeScore * 0.002f)) {
            float hx = random.nextFloat() * getWidth();
            float size = 18f + random.nextFloat() * 22f;
            float speed = 8f + random.nextFloat() * 10f + (dodgeScore * 0.1f);
            hazards.add(new Hazard(hx, -size, size, speed));
        }

        // Update hazards
        float shipRadius = 22f;
        for (int i = hazards.size() - 1; i >= 0; i--) {
            Hazard h = hazards.get(i);
            h.y += h.speed;

            // Collision check
            float dx = h.x - shipX;
            float dy = h.y - shipY;
            float dist = (float) Math.sqrt(dx * dx + dy * dy);
            if (dist < (shipRadius + h.size * 0.5f)) {
                // Ship Destroyed!
                isGameOver = true;
                CyberSoundSynth.get().playLaser();
                break;
            }

            // Scored past bottom
            if (h.y > getHeight() + 50) {
                hazards.remove(i);
                dodgeScore++;
                if (dodgeScore % 10 == 0) {
                    CyberSoundSynth.get().playChirp();
                }
            }
        }
    }

    private void updateCyberHack() {
        if (hackRevealing) {
            long elapsed = System.currentTimeMillis() - hackRevealStart;
            int totalRevealTime = (3 + hackLevel) * 450;
            if (elapsed > totalRevealTime) {
                hackRevealing = false;
            }
        } else if (!isGameOver) {
            if (System.currentTimeMillis() > hackTimerEnd) {
                isGameOver = true; // Timeout!
                CyberSoundSynth.get().playLaser();
            }
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int w = getWidth();
        int h = getHeight();
        if (w <= 0 || h <= 0) return;

        // Background
        canvas.drawColor(0xF5060A10);

        if (currentMode == GameMode.VECTOR_DODGE) {
            drawVectorDodge(canvas, w, h);
        } else {
            drawCyberHack(canvas, w, h);
        }

        // Top Header
        textPaint.setTextSize(28f);
        textPaint.setColor(HologramTheme.get().getPrimary());
        String modeTitle = currentMode == GameMode.VECTOR_DODGE ? "TACTICAL // VECTOR DODGE" : "SECURITY // CYBER HACK";
        canvas.drawText(modeTitle, w / 2f, 48f, textPaint);

        // Exit Button at top right
        textPaint.setTextSize(22f);
        canvas.drawText("[ EXIT ]", w - 70f, 48f, textPaint);

        // Bottom Remote Key Hints
        textPaint.setTextSize(18f);
        textPaint.setColor(0x8000F0FF);
        if (currentMode == GameMode.VECTOR_DODGE) {
            canvas.drawText("[D-PAD LEFT / RIGHT] STEER SHIP   [OK] RESTART   [BACK] EXIT", w / 2f, h - 24f, textPaint);
        } else {
            canvas.drawText("[D-PAD] MOVE RETICLE   [OK] EXECUTE NODE   [BACK] EXIT", w / 2f, h - 24f, textPaint);
        }
    }

    private void drawVectorDodge(Canvas canvas, int w, int h) {
        // Perspective Grid
        float gridYOffset = (System.currentTimeMillis() / 8f) % 60f;
        for (float y = gridYOffset; y < h; y += 60f) {
            canvas.drawLine(0, y, w, y, gridPaint);
        }

        // Hazards
        for (Hazard hz : hazards) {
            canvas.drawCircle(hz.x, hz.y, hz.size * 0.6f, hazardPaint);
        }

        // Ship
        shipPath.reset();
        shipPath.moveTo(shipX, shipY - 24f);
        shipPath.lineTo(shipX + 18f, shipY + 16f);
        shipPath.lineTo(shipX, shipY + 8f);
        shipPath.lineTo(shipX - 18f, shipY + 16f);
        shipPath.close();
        canvas.drawPath(shipPath, shipPaint);

        // Score
        textPaint.setTextSize(36f);
        textPaint.setColor(0xFFF0F8FF);
        canvas.drawText("SCORE: " + dodgeScore, w / 2f, 100f, textPaint);

        if (isGameOver) {
            textPaint.setColor(0xFFFF2A6D);
            textPaint.setTextSize(48f);
            canvas.drawText("SYSTEM COMPROMISED", w / 2f, h / 2f, textPaint);
            textPaint.setTextSize(26f);
            textPaint.setColor(0xFFF0F8FF);
            canvas.drawText("PRESS [OK] TO RE-ENGAGE", w / 2f, h / 2f + 60f, textPaint);
        }
    }

    private void drawCyberHack(Canvas canvas, int w, int h) {
        float gridSize = Math.min(w, h) * 0.72f;
        float startX = (w - gridSize) / 2f;
        float startY = (h - gridSize) / 2f;
        float cellSize = gridSize / HACK_GRID;

        long now = System.currentTimeMillis();
        int activeNode = -1;
        if (hackRevealing) {
            int step = (int) ((now - hackRevealStart) / 450);
            int seqLen = Math.min(3 + hackLevel, 8);
            if (step < seqLen) {
                activeNode = hackSequence[step];
            }
        }

        // Draw Nodes
        for (int row = 0; row < HACK_GRID; row++) {
            for (int col = 0; col < HACK_GRID; col++) {
                int nodeIdx = row * HACK_GRID + col;
                float nx = startX + (col * cellSize) + (cellSize * 0.1f);
                float ny = startY + (row * cellSize) + (cellSize * 0.1f);
                float side = cellSize * 0.8f;

                if (nodeIdx == activeNode) {
                    nodePaint.setColor(0xFF00FF66);
                } else if (playerInput.contains(nodeIdx)) {
                    nodePaint.setColor(HologramTheme.get().getPrimary());
                } else {
                    nodePaint.setColor(0x2000F0FF);
                }

                canvas.drawRect(nx, ny, nx + side, ny + side, nodePaint);

                // D-Pad Focus Reticle on TV Remote
                if (!hackRevealing && row == hackCursorRow && col == hackCursorCol) {
                    canvas.drawRect(nx - 3f, ny - 3f, nx + side + 3f, ny + side + 3f, cursorPaint);
                }

                // Monospace Hex label
                textPaint.setTextSize(20f);
                textPaint.setColor(0xFFF0F8FF);
                String hex = String.format("%02X", nodeIdx);
                canvas.drawText(hex, nx + (side / 2f), ny + (side / 2f) + 8f, textPaint);
            }
        }

        // Countdown timer bar
        if (!hackRevealing && !isGameOver) {
            float timeLeftFraction = Math.max(0f, (hackTimerEnd - now) / (float) (2500 + (hackLevel * 3000)));
            float barWidth = gridSize * timeLeftFraction;
            hazardPaint.setColor(HologramTheme.get().getPrimary());
            canvas.drawRect(startX, startY + gridSize + 20f, startX + barWidth, startY + gridSize + 32f, hazardPaint);
        }

        textPaint.setTextSize(32f);
        textPaint.setColor(0xFFF0F8FF);
        canvas.drawText("SECURITY LEVEL: " + hackLevel, w / 2f, startY - 30f, textPaint);

        if (isGameOver) {
            textPaint.setColor(0xFFFF2A6D);
            textPaint.setTextSize(44f);
            canvas.drawText("BREACH FAILED", w / 2f, h / 2f, textPaint);
            textPaint.setTextSize(24f);
            textPaint.setColor(0xFFF0F8FF);
            canvas.drawText("PRESS [OK] TO RETRY SECURITY BYPASS", w / 2f, h / 2f + 50f, textPaint);
        }
    }

    public void executeHackNode(int nodeIdx) {
        if (hackRevealing || isGameOver) return;

        CyberSoundSynth.get().playDataClick();
        playerInput.add(nodeIdx);

        int currentStep = playerInput.size() - 1;
        int seqLen = Math.min(3 + hackLevel, 8);

        if (hackSequence[currentStep] != nodeIdx) {
            // Wrong Node!
            isGameOver = true;
            CyberSoundSynth.get().playLaser();
        } else if (playerInput.size() == seqLen) {
            // Round Cleared!
            CyberSoundSynth.get().playPowerUp();
            hackLevel++;
            startNewHackRound();
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            CyberSoundSynth.get().playChirp();
            if (exitListener != null) {
                exitListener.onExit();
            }
            return true;
        }

        if (currentMode == GameMode.VECTOR_DODGE) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
                shipTargetX = Math.max(shipTargetX - 70f, 60f);
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                shipTargetX = Math.min(shipTargetX + 70f, getWidth() > 0 ? getWidth() - 60f : 1860f);
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER || keyCode == KeyEvent.KEYCODE_BUTTON_A) {
                if (isGameOver) {
                    CyberSoundSynth.get().playPowerUp();
                    resetGame();
                }
                return true;
            }
        } else if (currentMode == GameMode.CYBER_HACK) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP) {
                hackCursorRow = Math.max(0, hackCursorRow - 1);
                CyberSoundSynth.get().playDataClick();
                invalidate();
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) {
                hackCursorRow = Math.min(HACK_GRID - 1, hackCursorRow + 1);
                CyberSoundSynth.get().playDataClick();
                invalidate();
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
                hackCursorCol = Math.max(0, hackCursorCol - 1);
                CyberSoundSynth.get().playDataClick();
                invalidate();
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                hackCursorCol = Math.min(HACK_GRID - 1, hackCursorCol + 1);
                CyberSoundSynth.get().playDataClick();
                invalidate();
                return true;
            } else if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER || keyCode == KeyEvent.KEYCODE_BUTTON_A) {
                if (isGameOver) {
                    CyberSoundSynth.get().playPowerUp();
                    resetGame();
                } else if (!hackRevealing) {
                    int nodeIdx = hackCursorRow * HACK_GRID + hackCursorCol;
                    executeHackNode(nodeIdx);
                }
                return true;
            }
        }

        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (event.getAction() == MotionEvent.ACTION_DOWN) {
            // Check Exit button tap
            if (event.getY() < 80f && event.getX() > getWidth() - 140f) {
                CyberSoundSynth.get().playChirp();
                if (exitListener != null) exitListener.onExit();
                return true;
            }

            if (isGameOver) {
                CyberSoundSynth.get().playPowerUp();
                resetGame();
                return true;
            }

            if (currentMode == GameMode.VECTOR_DODGE) {
                // Touch steering
                shipTargetX = event.getX();
            } else if (currentMode == GameMode.CYBER_HACK && !hackRevealing) {
                // Node tap detection
                handleCyberHackTap(event.getX(), event.getY());
            }
            return true;
        } else if (event.getAction() == MotionEvent.ACTION_MOVE && currentMode == GameMode.VECTOR_DODGE) {
            shipTargetX = event.getX();
            return true;
        }
        return super.onTouchEvent(event);
    }

    private void handleCyberHackTap(float x, float y) {
        float gridSize = Math.min(getWidth(), getHeight()) * 0.72f;
        float startX = (getWidth() - gridSize) / 2f;
        float startY = (getHeight() - gridSize) / 2f;
        float cellSize = gridSize / HACK_GRID;

        int col = (int) ((x - startX) / cellSize);
        int row = (int) ((y - startY) / cellSize);

        if (col >= 0 && col < HACK_GRID && row >= 0 && row < HACK_GRID) {
            hackCursorRow = row;
            hackCursorCol = col;
            int nodeIdx = row * HACK_GRID + col;
            executeHackNode(nodeIdx);
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        if (gameLoop != null) gameLoop.cancel();
    }
}
