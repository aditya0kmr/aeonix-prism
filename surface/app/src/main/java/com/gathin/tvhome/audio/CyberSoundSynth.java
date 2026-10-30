package com.gathin.tvhome.audio;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Build;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CyberSoundSynth {

    private static CyberSoundSynth instance;
    private final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    private boolean enabled = true;
    private static final int SAMPLE_RATE = 22050;

    private static final short[] DATA_CLICK_BUFFER;
    private static final short[] CHIRP_BUFFER;
    private static final short[] POWER_UP_BUFFER;
    private static final short[] WARP_BUFFER;
    private static final short[] LASER_BUFFER;

    static {
        // Pre-compute DATA_CLICK_BUFFER (15ms @ 22050Hz)
        int durationMs = 15;
        int numSamples = (SAMPLE_RATE * durationMs) / 1000;
        DATA_CLICK_BUFFER = new short[numSamples];
        for (int i = 0; i < numSamples; i++) {
            double t = (double) i / SAMPLE_RATE;
            double freq = 2400.0;
            double envelope = 1.0 - ((double) i / numSamples);
            double sample = Math.sin(2.0 * Math.PI * freq * t) * envelope;
            DATA_CLICK_BUFFER[i] = (short) (sample * 14000);
        }

        // Pre-compute CHIRP_BUFFER (60ms @ 22050Hz)
        durationMs = 60;
        numSamples = (SAMPLE_RATE * durationMs) / 1000;
        CHIRP_BUFFER = new short[numSamples];
        for (int i = 0; i < numSamples; i++) {
            double t = (double) i / SAMPLE_RATE;
            double progress = (double) i / numSamples;
            double freq = 900.0 + (progress * 1600.0);
            double envelope = Math.sin(Math.PI * progress);
            double sample = Math.sin(2.0 * Math.PI * freq * t) * envelope;
            CHIRP_BUFFER[i] = (short) (sample * 18000);
        }

        // Pre-compute POWER_UP_BUFFER (280ms @ 22050Hz)
        durationMs = 280;
        numSamples = (SAMPLE_RATE * durationMs) / 1000;
        POWER_UP_BUFFER = new short[numSamples];
        for (int i = 0; i < numSamples; i++) {
            double t = (double) i / SAMPLE_RATE;
            double progress = (double) i / numSamples;
            double freq = 80.0 + (Math.pow(progress, 2.0) * 520.0);
            double envelope = Math.sin(Math.PI * Math.sqrt(progress));
            double sample = Math.sin(2.0 * Math.PI * freq * t) * envelope;
            sample += 0.3 * Math.sin(4.0 * Math.PI * freq * t) * envelope;
            POWER_UP_BUFFER[i] = (short) (Math.min(1.0, Math.max(-1.0, sample)) * 20000);
        }

        // Pre-compute WARP_BUFFER (180ms @ 22050Hz)
        durationMs = 180;
        numSamples = (SAMPLE_RATE * durationMs) / 1000;
        WARP_BUFFER = new short[numSamples];
        for (int i = 0; i < numSamples; i++) {
            double t = (double) i / SAMPLE_RATE;
            double progress = (double) i / numSamples;
            double freq = 1400.0 - (progress * 900.0);
            double envelope = 1.0 - progress;
            double sample = (Math.sin(2.0 * Math.PI * freq * t) > 0 ? 0.7 : -0.7) * envelope;
            WARP_BUFFER[i] = (short) (sample * 16000);
        }

        // Pre-compute LASER_BUFFER (90ms @ 22050Hz)
        durationMs = 90;
        numSamples = (SAMPLE_RATE * durationMs) / 1000;
        LASER_BUFFER = new short[numSamples];
        for (int i = 0; i < numSamples; i++) {
            double t = (double) i / SAMPLE_RATE;
            double progress = (double) i / numSamples;
            double freq = 2200.0 * Math.exp(-progress * 4.0);
            double envelope = 1.0 - progress;
            double sample = Math.sin(2.0 * Math.PI * freq * t) * envelope;
            LASER_BUFFER[i] = (short) (sample * 19000);
        }
    }

    private CyberSoundSynth() {}

    public static synchronized CyberSoundSynth get() {
        if (instance == null) {
            instance = new CyberSoundSynth();
        }
        return instance;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void playDataClick() {
        if (!enabled) return;
        audioExecutor.execute(() -> playPcm(DATA_CLICK_BUFFER));
    }

    public void playChirp() {
        if (!enabled) return;
        audioExecutor.execute(() -> playPcm(CHIRP_BUFFER));
    }

    public void playPowerUp() {
        if (!enabled) return;
        audioExecutor.execute(() -> playPcm(POWER_UP_BUFFER));
    }

    public void playWarp() {
        if (!enabled) return;
        audioExecutor.execute(() -> playPcm(WARP_BUFFER));
    }

    public void playLaser() {
        if (!enabled) return;
        audioExecutor.execute(() -> playPcm(LASER_BUFFER));
    }

    private void playPcm(short[] pcm) {
        AudioTrack track = null;
        try {
            int minBuffer = AudioTrack.getMinBufferSize(
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
            );
            int bufferSize = Math.max(pcm.length * 2, minBuffer);

            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();

            AudioFormat format = new AudioFormat.Builder()
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(SAMPLE_RATE)
                    .build();

            track = new AudioTrack(
                    attributes,
                    format,
                    bufferSize,
                    AudioTrack.MODE_STATIC,
                    0
            );

            track.write(pcm, 0, pcm.length);
            track.play();
            // Wait slightly for playback to complete
            Thread.sleep((pcm.length * 1000L) / SAMPLE_RATE + 20);
        } catch (Exception ignored) {
        } finally {
            if (track != null) {
                try {
                    track.stop();
                    track.release();
                } catch (Exception ignored) {}
            }
        }
    }
}
