package com.gathin.tvhome.net;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Ultra-Lightweight Sovereign WebSocket Client (<100KB RAM overhead)
 * Connects directly to POCO Core Mind (ws://10.116.23.168:8080/ws)
 * Features:
 * - Fire OS Wi-Fi power-save sleep/wake resilience
 * - Exponential backoff reconnection with random jitter and max ceiling
 * - Bounded local event queue (max 50 events, drop-oldest overflow policy)
 * - Strict Zero-Trust offline security: Sensitive actions/approvals/missions are rejected from queue
 * - mDNS fallback discovery and TLS certificate pinning
 */
public class AeonixWebSocketClient {
    private static final String TAG = "AeonixWS";
    private static final String DEFAULT_HOST = "10.116.23.168";
    private static final int DEFAULT_PORT = 8080;
    private static final String SERVICE_TYPE = "_aeonix._tcp.";

    public static final int INITIAL_BACKOFF_MS = 1000;
    public static final int MAX_BACKOFF_MS = 16000;
    public static final double BACKOFF_MULTIPLIER = 2.0;
    public static final int MAX_QUEUE_CAPACITY = 50;

    private static void logD(String tag, String msg) {
        try { Log.d(tag, msg); } catch (Throwable ignored) {}
    }
    private static void logI(String tag, String msg) {
        try { Log.i(tag, msg); } catch (Throwable ignored) {}
    }
    private static void logW(String tag, String msg) {
        try { Log.w(tag, msg); } catch (Throwable ignored) {}
    }
    private static void logE(String tag, String msg) {
        try { Log.e(tag, msg); } catch (Throwable ignored) {}
    }

    public String loadProvisionedToken() {
        if (context == null) return "";
        try {
            File authFile = new File(context.getFilesDir(), "auth/glass_token.json");
            if (authFile.exists() && authFile.canRead()) {
                byte[] data = new byte[(int) authFile.length()];
                try (FileInputStream fis = new FileInputStream(authFile)) {
                    int read = fis.read(data);
                    if (read > 0) {
                        JSONObject obj = new JSONObject(new String(data, 0, read, StandardCharsets.UTF_8));
                        return obj.optString("token", "").trim();
                    }
                }
            }
        } catch (Exception e) {
            logW(TAG, "Failed to load provisioned token: " + e.getMessage());
        }
        return "";
    }

    public String loadPinnedFingerprint() {
        if (context == null) return "";
        try {
            File pinFile = new File(context.getFilesDir(), "auth/cert_pin.json");
            if (pinFile.exists() && pinFile.canRead()) {
                byte[] data = new byte[(int) pinFile.length()];
                try (FileInputStream fis = new FileInputStream(pinFile)) {
                    int read = fis.read(data);
                    if (read > 0) {
                        JSONObject obj = new JSONObject(new String(data, 0, read, StandardCharsets.UTF_8));
                        return obj.optString("sha256_fingerprint", "").trim();
                    }
                }
            }
        } catch (Exception e) {
            logW(TAG, "Failed to load pinned certificate fingerprint: " + e.getMessage());
        }
        return "";
    }

    public static X509TrustManager createPinnedTrustManager(String expectedFingerprint) {
        if (expectedFingerprint == null || expectedFingerprint.trim().isEmpty()) {
            throw new IllegalArgumentException("MISSING_PIN: Certificate pin cannot be null or empty. Plaintext fallback prohibited.");
        }
        final String cleanExpected = expectedFingerprint.replaceAll("[:\\s]", "").toUpperCase();
        return new X509TrustManager() {
            @Override
            public void checkClientTrusted(X509Certificate[] chain, String authType) {}

            @Override
            public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
                if (chain == null || chain.length == 0) {
                    throw new CertificateException("Empty certificate chain");
                }
                X509Certificate cert = chain[0];
                try {
                    MessageDigest md = MessageDigest.getInstance("SHA-256");
                    byte[] der = cert.getEncoded();
                    byte[] digest = md.digest(der);
                    StringBuilder sb = new StringBuilder();
                    for (byte b : digest) {
                        sb.append(String.format("%02X", b));
                    }
                    String actualFingerprint = sb.toString();
                    if (!actualFingerprint.equalsIgnoreCase(cleanExpected)) {
                        throw new CertificateException("Certificate pin mismatch! Expected " + cleanExpected + " but got " + actualFingerprint);
                    }
                } catch (Exception e) {
                    if (e instanceof CertificateException) throw (CertificateException) e;
                    throw new CertificateException("Error verifying certificate fingerprint", e);
                }
            }

            @Override
            public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        };
    }

    public static SSLSocketFactory getPinnedSSLSocketFactory(String expectedFingerprint) throws Exception {
        TrustManager[] trustManagers = new TrustManager[]{ createPinnedTrustManager(expectedFingerprint) };
        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(null, trustManagers, new SecureRandom());
        return sslContext.getSocketFactory();
    }

    /**
     * Determines whether a payload is a sensitive action that must NEVER be queued,
     * replayed, or executed while offline (Sentinel approvals, mission claims, destructive actions, OSINT).
     */
    public static boolean isSensitiveAction(String payload) {
        if (payload == null || payload.trim().isEmpty()) return false;
        try {
            JSONObject obj = new JSONObject(payload);
            String type = obj.optString("type", "").toLowerCase();
            if (type.equals("sentinel_action") ||
                type.equals("sentinel_approval") ||
                type.equals("sentinel_response") ||
                type.equals("sentinel_claim") ||
                type.equals("sentinel_card") ||
                type.equals("sentinel_request") ||
                type.equals("sentinel_resolved") ||
                type.equals("mission_claim") ||
                type.equals("mission_execute") ||
                type.equals("consequential_mission") ||
                type.equals("file_delete") ||
                type.equals("destructive_action") ||
                type.equals("wipe") ||
                type.equals("sanctuary_toggle") ||
                type.equals("osint_query") ||
                type.equals("terminal_cmd") ||
                type.equals("shell_exec")) {
                return true;
            }
            if (obj.has("request_id") && (obj.has("approved") || obj.has("approval"))) {
                return true;
            }
            if (obj.has("mission_id") && (obj.has("execute") || obj.has("claim"))) {
                return true;
            }
        } catch (Throwable ignored) {
            String lower = payload.toLowerCase();
            if (lower.contains("sentinel_action") ||
                lower.contains("sentinel_approval") ||
                lower.contains("mission_claim") ||
                lower.contains("mission_execute") ||
                lower.contains("file_delete") ||
                lower.contains("destructive_action") ||
                lower.contains("wipe") ||
                lower.contains("osint_query") ||
                lower.contains("terminal_cmd") ||
                (lower.contains("request_id") && (lower.contains("approved") || lower.contains("approval"))) ||
                (lower.contains("mission_id") && (lower.contains("execute") || lower.contains("claim")))) {
                return true;
            }
        }
        return false;
    }

    public interface Listener {
        void onConnected();
        void onDisconnected(String reason);
        void onMessage(String payload);
        void onError(Throwable t);
        default void onSleep() {}
        default void onWake() {}
    }

    private final Context context;
    private final Listener listener;
    private final Handler mainHandler;
    private final AtomicBoolean isRunning = new AtomicBoolean(false);
    private final AtomicBoolean isConnected = new AtomicBoolean(false);
    private final AtomicBoolean isSleeping = new AtomicBoolean(false);

    private final Object reconnectLock = new Object();
    private volatile boolean forceReconnectRequested = false;

    // Bounded local event queue (Requirement 5 & 6)
    private final ConcurrentLinkedQueue<String> eventQueue = new ConcurrentLinkedQueue<>();
    private final AtomicLong queuedCount = new AtomicLong(0);
    private final AtomicLong droppedEventCount = new AtomicLong(0);
    private final AtomicLong flushedEventCount = new AtomicLong(0);
    private final AtomicLong reconnectCount = new AtomicLong(0);
    private volatile String lastDisconnectReason = "INITIALIZING";

    private String targetHost = DEFAULT_HOST;
    private int targetPort = DEFAULT_PORT;

    private Socket socket;
    private OutputStream outStream;
    private Thread workerThread;
    private Thread heartbeatThread;
    private NsdManager nsdManager;
    private NsdManager.DiscoveryListener discoveryListener;
    private BroadcastReceiver powerAndNetworkReceiver;

    public AeonixWebSocketClient(Context context, Listener listener) {
        this.context = (context != null) ? context.getApplicationContext() : null;
        this.listener = listener;
        Handler h = null;
        try {
            if (Looper.myLooper() != null || Looper.getMainLooper() != null) {
                h = new Handler(Looper.getMainLooper() != null ? Looper.getMainLooper() : Looper.myLooper());
            }
        } catch (Exception ignored) {}
        this.mainHandler = h;

        if (this.context != null) {
            initMdnsDiscovery();
        }
    }

    private void initMdnsDiscovery() {
        if (context == null) return;
        try {
            nsdManager = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
            if (nsdManager == null) return;
            discoveryListener = new NsdManager.DiscoveryListener() {
                @Override
                public void onStartDiscoveryFailed(String serviceType, int errorCode) {}

                @Override
                public void onStopDiscoveryFailed(String serviceType, int errorCode) {}

                @Override
                public void onDiscoveryStarted(String serviceType) {}

                @Override
                public void onDiscoveryStopped(String serviceType) {}

                @Override
                public void onServiceFound(NsdServiceInfo serviceInfo) {
                    if (serviceInfo.getServiceType().contains("aeonix")) {
                        try {
                            nsdManager.resolveService(serviceInfo, new NsdManager.ResolveListener() {
                                @Override
                                public void onResolveFailed(NsdServiceInfo serviceInfo, int errorCode) {}

                                @Override
                                public void onServiceResolved(NsdServiceInfo resolved) {
                                    if (resolved.getHost() != null) {
                                        targetHost = resolved.getHost().getHostAddress();
                                        targetPort = resolved.getPort();
                                        logI(TAG, "mDNS resolved Core Mind at: " + targetHost + ":" + targetPort);
                                    }
                                }
                            });
                        } catch (Exception ignored) {}
                    }
                }

                @Override
                public void onServiceLost(NsdServiceInfo serviceInfo) {}
            };
            nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, discoveryListener);
        } catch (Exception e) {
            logW(TAG, "mDNS discovery not supported or failed: " + e.getMessage());
        }
    }

    private void registerReceivers() {
        if (context == null || powerAndNetworkReceiver != null) return;
        try {
            powerAndNetworkReceiver = new BroadcastReceiver() {
                @Override
                public void onReceive(Context ctx, Intent intent) {
                    if (intent == null || intent.getAction() == null) return;
                    String action = intent.getAction();
                    if (Intent.ACTION_SCREEN_OFF.equals(action)) {
                        logI(TAG, "Detected Fire OS ACTION_SCREEN_OFF (Wi-Fi power-save sleep initiated)");
                        isSleeping.set(true);
                        lastDisconnectReason = "POWER_SAVE_SLEEP";
                        closeSocket();
                        notifySleep();
                        notifyDisconnected("POWER_SAVE_SLEEP");
                    } else if (Intent.ACTION_SCREEN_ON.equals(action)) {
                        logI(TAG, "Detected Fire OS ACTION_SCREEN_ON (Device wake detected)");
                        isSleeping.set(false);
                        notifyWake();
                        reconnectImmediately();
                    } else if (ConnectivityManager.CONNECTIVITY_ACTION.equals(action)) {
                        ConnectivityManager cm = (ConnectivityManager) ctx.getSystemService(Context.CONNECTIVITY_SERVICE);
                        NetworkInfo netInfo = (cm != null) ? cm.getActiveNetworkInfo() : null;
                        boolean isOnline = (netInfo != null && netInfo.isConnected());
                        logD(TAG, "Connectivity state change: online=" + isOnline);
                        if (isOnline && !isConnected.get() && !isSleeping.get()) {
                            reconnectImmediately();
                        } else if (!isOnline && isConnected.get()) {
                            lastDisconnectReason = "NETWORK_DISCONNECTED";
                            closeSocket();
                            notifyDisconnected("NETWORK_DISCONNECTED");
                        }
                    }
                }
            };
            IntentFilter filter = new IntentFilter();
            filter.addAction(Intent.ACTION_SCREEN_OFF);
            filter.addAction(Intent.ACTION_SCREEN_ON);
            filter.addAction(ConnectivityManager.CONNECTIVITY_ACTION);
            context.registerReceiver(powerAndNetworkReceiver, filter);
        } catch (Exception e) {
            logW(TAG, "Failed to register power/network receivers: " + e.getMessage());
        }
    }

    private void unregisterReceivers() {
        if (context != null && powerAndNetworkReceiver != null) {
            try {
                context.unregisterReceiver(powerAndNetworkReceiver);
            } catch (Exception ignored) {}
            powerAndNetworkReceiver = null;
        }
    }

    public synchronized void start() {
        if (isRunning.getAndSet(true)) return;

        registerReceivers();
        workerThread = new Thread(this::runConnectionLoop, "AeonixWS-Worker");
        workerThread.start();
    }

    public synchronized void stop() {
        isRunning.set(false);
        unregisterReceivers();
        closeSocket();
        reconnectImmediately();
        if (workerThread != null) {
            workerThread.interrupt();
            workerThread = null;
        }
        if (heartbeatThread != null) {
            heartbeatThread.interrupt();
            heartbeatThread = null;
        }
        if (nsdManager != null && discoveryListener != null) {
            try {
                nsdManager.stopServiceDiscovery(discoveryListener);
            } catch (Exception ignored) {}
        }
        stopVoiceRecording();
    }

    public void reconnectImmediately() {
        forceReconnectRequested = true;
        synchronized (reconnectLock) {
            reconnectLock.notifyAll();
        }
        if (workerThread != null) {
            workerThread.interrupt();
        }
    }

    private AudioRecord audioRecord;
    private Thread recordingThread;
    private final AtomicBoolean isRecording = new AtomicBoolean(false);

    public synchronized void startVoiceRecording() {
        if (!isConnected.get() || isRecording.getAndSet(true)) return;

        sendText("{\"type\":\"audio_start\"}");
        recordingThread = new Thread(() -> {
            try {
                int sampleRate = 16000;
                int channelConfig = AudioFormat.CHANNEL_IN_MONO;
                int audioFormat = AudioFormat.ENCODING_PCM_16BIT;
                int minBufSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat);
                int bufferSize = Math.max(minBufSize, 4096);

                audioRecord = new AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                );

                if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                    logE(TAG, "AudioRecord failed to initialize");
                    isRecording.set(false);
                    return;
                }

                audioRecord.startRecording();
                byte[] audioBuf = new byte[2048];
                long recordStartTime = System.currentTimeMillis();
                long maxRecordingDurationMs = 15000; // Hard bounded at 15 seconds to prevent runaway buffering

                while (isRecording.get()) {
                    if (System.currentTimeMillis() - recordStartTime > maxRecordingDurationMs) {
                        logW(TAG, "Audio recording hit 15s safety duration ceiling. Terminating stream.");
                        break;
                    }
                    int read = audioRecord.read(audioBuf, 0, audioBuf.length);
                    if (read > 0) {
                        byte[] chunk = new byte[read];
                        System.arraycopy(audioBuf, 0, chunk, 0, read);
                        String b64 = Base64.encodeToString(chunk, Base64.NO_WRAP);
                        sendText("{\"type\":\"audio_chunk\",\"data\":\"" + b64 + "\"}");
                    }
                }
            } catch (Exception e) {
                logE(TAG, "Audio recording error: " + e.getMessage());
            } finally {
                if (audioRecord != null) {
                    try {
                        audioRecord.stop();
                        audioRecord.release();
                    } catch (Exception ignored) {}
                    audioRecord = null;
                }
                sendText("{\"type\":\"audio_end\"}");
                isRecording.set(false);
            }
        }, "Aeonix-AudioRecord");
        recordingThread.start();
    }

    public synchronized void stopVoiceRecording() {
        isRecording.set(false);
    }

    public boolean isVoiceRecording() {
        return isRecording.get();
    }

    private void runConnectionLoop() {
        int backoffMs = INITIAL_BACKOFF_MS;
        while (isRunning.get()) {
            if (isSleeping.get()) {
                logD(TAG, "Device is in Wi-Fi power-save sleep. Pausing reconnect loop until wake.");
                synchronized (reconnectLock) {
                    try {
                        reconnectLock.wait(60000);
                    } catch (InterruptedException ignored) {}
                }
                if (!isRunning.get()) break;
                if (isSleeping.get()) continue;
            }

            try {
                logD(TAG, "Attempting connection to ws://" + targetHost + ":" + targetPort + "/ws");
                forceReconnectRequested = false;
                connectAndListen();
                backoffMs = INITIAL_BACKOFF_MS; // Reset backoff on clean connection
            } catch (Exception e) {
                String reason = isSleeping.get() ? "POWER_SAVE_SLEEP" : ("Connection failed: " + e.getMessage());
                lastDisconnectReason = reason;
                notifyDisconnected(reason);
                logW(TAG, "Connection dropped (" + reason + "), retrying in " + backoffMs + "ms");
            }

            if (!isRunning.get()) break;

            int jitter = (int) (Math.random() * 500);
            int sleepTime = Math.min(backoffMs + jitter, MAX_BACKOFF_MS);
            backoffMs = Math.min((int) (backoffMs * BACKOFF_MULTIPLIER), MAX_BACKOFF_MS);

            synchronized (reconnectLock) {
                if (forceReconnectRequested) {
                    forceReconnectRequested = false;
                    backoffMs = INITIAL_BACKOFF_MS;
                    continue;
                }
                try {
                    reconnectLock.wait(sleepTime);
                } catch (InterruptedException ie) {
                    if (forceReconnectRequested) {
                        forceReconnectRequested = false;
                        backoffMs = INITIAL_BACKOFF_MS;
                    }
                }
            }
        }
    }

    private void connectAndListen() throws Exception {
        String pinnedFp = loadPinnedFingerprint();
        if (pinnedFp == null || pinnedFp.trim().isEmpty()) {
            throw new IllegalStateException("NO_PIN_PROVISIONED: Sovereign glass terminal strictly mandates a valid provisioned certificate pin. Plaintext fallback prohibited.");
        }

        logI(TAG, "Initiating Sovereign TLS Handshake with certificate pinning");
        SSLSocketFactory sslFactory = getPinnedSSLSocketFactory(pinnedFp.trim());
        SSLSocket sslSocket = (SSLSocket) sslFactory.createSocket();
        sslSocket.connect(new InetSocketAddress(targetHost, targetPort), 5000);
        sslSocket.setTcpNoDelay(true);
        sslSocket.startHandshake();
        socket = sslSocket;

        InputStream in = socket.getInputStream();
        outStream = socket.getOutputStream();

        // Load provisioned token from secure app storage
        String token = loadProvisionedToken();
        if (token.isEmpty()) {
            throw new IllegalStateException("NO_PROVISIONED_CREDENTIAL: Glass terminal token not found in app storage");
        }

        // Perform RFC 6455 Handshake with header-based authorization
        byte[] nonce = new byte[16];
        new SecureRandom().nextBytes(nonce);
        String secKey = Base64.encodeToString(nonce, Base64.NO_WRAP);

        String handshake = "GET /ws HTTP/1.1\r\n" +
                "Host: " + targetHost + ":" + targetPort + "\r\n" +
                "Upgrade: websocket\r\n" +
                "Connection: Upgrade\r\n" +
                "Authorization: Bearer " + token + "\r\n" +
                "Sec-WebSocket-Key: " + secKey + "\r\n" +
                "Sec-WebSocket-Version: 13\r\n\r\n";

        outStream.write(handshake.getBytes(StandardCharsets.UTF_8));
        outStream.flush();

        // Read HTTP response headers
        ByteArrayOutputStream headerBuf = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) != -1) {
            headerBuf.write(b);
            byte[] bytes = headerBuf.toByteArray();
            if (bytes.length >= 4 &&
                    bytes[bytes.length - 4] == '\r' &&
                    bytes[bytes.length - 3] == '\n' &&
                    bytes[bytes.length - 2] == '\r' &&
                    bytes[bytes.length - 1] == '\n') {
                break;
            }
        }

        String headers = headerBuf.toString("UTF-8");
        if (!headers.contains("101 Switching Protocols")) {
            throw new IllegalStateException("Handshake failed: " + headers);
        }

        isConnected.set(true);
        reconnectCount.incrementAndGet();
        notifyConnected();
        flushEventQueue();
        startHeartbeat();

        // Frame read loop
        while (isRunning.get()) {
            int b1 = in.read();
            if (b1 == -1) break;

            int opcode = b1 & 0x0F;
            int b2 = in.read();
            if (b2 == -1) break;

            boolean masked = (b2 & 0x80) != 0;
            long payloadLen = b2 & 0x7F;

            if (payloadLen == 126) {
                int h = in.read();
                int l = in.read();
                payloadLen = ((h << 8) | l);
            } else if (payloadLen == 127) {
                payloadLen = 0;
                for (int i = 0; i < 8; i++) {
                    payloadLen = (payloadLen << 8) | in.read();
                }
            }

            byte[] maskKey = null;
            if (masked) {
                maskKey = new byte[4];
                in.read(maskKey);
            }

            byte[] payload = new byte[(int) payloadLen];
            int read = 0;
            while (read < payloadLen) {
                int r = in.read(payload, read, (int) payloadLen - read);
                if (r == -1) break;
                read += r;
            }

            if (masked && maskKey != null) {
                for (int i = 0; i < payload.length; i++) {
                    payload[i] ^= maskKey[i % 4];
                }
            }

            if (opcode == 0x1) { // Text
                String text = new String(payload, StandardCharsets.UTF_8);
                notifyMessage(text);
            } else if (opcode == 0x9) { // Ping
                sendPong(payload);
            } else if (opcode == 0x8) { // Close
                break;
            }
        }

        closeSocket();
    }

    private void startHeartbeat() {
        if (heartbeatThread != null) heartbeatThread.interrupt();
        heartbeatThread = new Thread(() -> {
            while (isConnected.get() && isRunning.get()) {
                try {
                    Thread.sleep(5000);
                    sendImmediately("{\"type\":\"ping\"}");
                } catch (InterruptedException ie) {
                    break;
                } catch (Exception e) {
                    break;
                }
            }
        }, "AeonixWS-Heartbeat");
        heartbeatThread.start();
    }

    /**
     * Sends a text message. If connected, sends immediately.
     * If disconnected:
     * - Drops sensitive actions (Sentinel approvals, mission execution, etc.) per Zero-Trust Policy.
     * - Queues non-sensitive UI/state events into bounded queue (max 50, drop oldest on overflow).
     */
    public synchronized void sendText(String message) {
        if (message == null) return;

        if (isConnected.get() && outStream != null) {
            sendImmediately(message);
            return;
        }

        // Offline event handling
        if (isSensitiveAction(message)) {
            logW(TAG, "DROPPED SENSITIVE ACTION: Sensitive command rejected while offline (Zero-Trust Policy): " + message);
            return;
        }

        // Bounded queue: drop oldest when saturated
        while (eventQueue.size() >= MAX_QUEUE_CAPACITY) {
            String dropped = eventQueue.poll();
            if (dropped != null) {
                droppedEventCount.incrementAndGet();
                logW(TAG, "Event queue saturated (" + MAX_QUEUE_CAPACITY + "). Dropped oldest non-sensitive event. Total dropped: " + droppedEventCount.get());
            }
        }
        eventQueue.offer(message);
        queuedCount.incrementAndGet();
        logD(TAG, "Queued non-sensitive event while offline. Current queue size: " + eventQueue.size());
    }

    private void flushEventQueue() {
        if (!isConnected.get() || outStream == null) return;
        int count = 0;
        String event;
        while ((event = eventQueue.poll()) != null) {
            if (!isSensitiveAction(event)) {
                sendImmediately(event);
                count++;
                flushedEventCount.incrementAndGet();
            }
        }
        if (count > 0) {
            logI(TAG, "Flushed " + count + " queued non-sensitive events upon reconnect.");
        }
    }

    private void sendImmediately(String message) {
        new Thread(() -> {
            try {
                OutputStream os = outStream;
                if (os == null || !isConnected.get()) {
                    if (!isSensitiveAction(message)) {
                        eventQueue.offer(message);
                    }
                    return;
                }
                byte[] raw = message.getBytes(StandardCharsets.UTF_8);
                byte[] frame = encodeClientFrame(0x1, raw);
                synchronized (os) {
                    os.write(frame);
                    os.flush();
                }
            } catch (Exception e) {
                logW(TAG, "Error sending frame: " + e.getMessage());
                closeSocket();
            }
        }, "AeonixWS-Send").start();
    }

    private void sendPong(byte[] appData) {
        try {
            OutputStream os = outStream;
            if (os == null) return;
            byte[] frame = encodeClientFrame(0xA, appData);
            synchronized (os) {
                os.write(frame);
                os.flush();
            }
        } catch (Exception ignored) {}
    }

    private byte[] encodeClientFrame(int opcode, byte[] payload) {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        baos.write(0x80 | (opcode & 0x0F)); // FIN + opcode

        int len = payload.length;
        byte[] mask = new byte[4];
        new SecureRandom().nextBytes(mask);

        if (len <= 125) {
            baos.write(0x80 | len);
        } else if (len <= 65535) {
            baos.write(0x80 | 126);
            baos.write((len >> 8) & 0xFF);
            baos.write(len & 0xFF);
        } else {
            baos.write(0x80 | 127);
            for (int i = 7; i >= 0; i--) {
                baos.write((len >> (8 * i)) & 0xFF);
            }
        }

        baos.write(mask, 0, 4);
        for (int i = 0; i < len; i++) {
            baos.write(payload[i] ^ mask[i % 4]);
        }
        return baos.toByteArray();
    }

    private void closeSocket() {
        isConnected.set(false);
        try {
            if (socket != null && !socket.isClosed()) socket.close();
        } catch (Exception ignored) {}
        socket = null;
        outStream = null;
    }

    private void notifyConnected() {
        if (mainHandler != null) {
            mainHandler.post(listener::onConnected);
        } else {
            listener.onConnected();
        }
    }

    private void notifyDisconnected(String reason) {
        if (mainHandler != null) {
            mainHandler.post(() -> listener.onDisconnected(reason));
        } else {
            listener.onDisconnected(reason);
        }
    }

    private void notifyMessage(String msg) {
        if (mainHandler != null) {
            mainHandler.post(() -> listener.onMessage(msg));
        } else {
            listener.onMessage(msg);
        }
    }

    private void notifySleep() {
        if (mainHandler != null) {
            mainHandler.post(listener::onSleep);
        } else {
            listener.onSleep();
        }
    }

    private void notifyWake() {
        if (mainHandler != null) {
            mainHandler.post(listener::onWake);
        } else {
            listener.onWake();
        }
    }

    // Telemetry and observation getters
    public int getQueueSize() {
        return eventQueue.size();
    }

    public long getDroppedEventCount() {
        return droppedEventCount.get();
    }

    public long getFlushedEventCount() {
        return flushedEventCount.get();
    }

    public long getReconnectCount() {
        return reconnectCount.get();
    }

    public String getLastDisconnectReason() {
        return lastDisconnectReason;
    }

    public boolean isSleeping() {
        return isSleeping.get();
    }

    public boolean isConnected() {
        return isConnected.get();
    }
}
