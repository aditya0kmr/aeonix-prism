package com.gathin.tvhome.net;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.security.SecureRandom;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Ultra-Lightweight Sovereign WebSocket Client (<100KB RAM overhead)
 * Connects directly to POCO Core Mind (ws://10.116.23.168:8080/ws)
 * Features mDNS fallback discovery and automatic exponential backoff reconnection.
 */
public class AeonixWebSocketClient {
    private static final String TAG = "AeonixWS";
    private static final String DEFAULT_HOST = "10.116.23.168";
    private static final int DEFAULT_PORT = 8080;
    private static final String SERVICE_TYPE = "_aeonix._tcp.";

    public interface Listener {
        void onConnected();
        void onDisconnected(String reason);
        void onMessage(String payload);
        void onError(Throwable t);
    }

    private final Context context;
    private final Listener listener;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean isRunning = new AtomicBoolean(false);
    private final AtomicBoolean isConnected = new AtomicBoolean(false);

    private String targetHost = DEFAULT_HOST;
    private int targetPort = DEFAULT_PORT;

    private Socket socket;
    private OutputStream outStream;
    private Thread workerThread;
    private Thread heartbeatThread;
    private NsdManager nsdManager;
    private NsdManager.DiscoveryListener discoveryListener;

    public AeonixWebSocketClient(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
        initMdnsDiscovery();
    }

    private void initMdnsDiscovery() {
        try {
            nsdManager = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
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
                                        Log.i(TAG, "mDNS resolved Core Mind at: " + targetHost + ":" + targetPort);
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
            Log.w(TAG, "mDNS discovery not supported or failed: " + e.getMessage());
        }
    }

    public synchronized void start() {
        if (isRunning.getAndSet(true)) return;

        workerThread = new Thread(this::runConnectionLoop, "AeonixWS-Worker");
        workerThread.start();
    }

    public synchronized void stop() {
        isRunning.set(false);
        closeSocket();
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
                    Log.e(TAG, "AudioRecord failed to initialize");
                    isRecording.set(false);
                    return;
                }

                audioRecord.startRecording();
                byte[] audioBuf = new byte[2048];

                while (isRecording.get()) {
                    int read = audioRecord.read(audioBuf, 0, audioBuf.length);
                    if (read > 0) {
                        byte[] chunk = new byte[read];
                        System.arraycopy(audioBuf, 0, chunk, 0, read);
                        String b64 = Base64.encodeToString(chunk, Base64.NO_WRAP);
                        sendText("{\"type\":\"audio_chunk\",\"data\":\"" + b64 + "\"}");
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Audio recording error: " + e.getMessage());
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
        int backoffMs = 1000;
        while (isRunning.get()) {
            try {
                Log.d(TAG, "Attempting connection to ws://" + targetHost + ":" + targetPort + "/ws");
                connectAndListen();
                backoffMs = 1000; // Reset backoff on clean run
            } catch (Exception e) {
                notifyDisconnected("Connection failed: " + e.getMessage());
                Log.w(TAG, "Connection dropped, retrying in " + backoffMs + "ms: " + e.getMessage());
            }

            try {
                Thread.sleep(backoffMs);
                backoffMs = Math.min(backoffMs * 2, 10000);
            } catch (InterruptedException ie) {
                break;
            }
        }
    }

    private void connectAndListen() throws Exception {
        socket = new Socket();
        socket.connect(new InetSocketAddress(targetHost, targetPort), 5000);
        socket.setTcpNoDelay(true);

        InputStream in = socket.getInputStream();
        outStream = socket.getOutputStream();

        // Perform RFC 6455 Handshake
        byte[] nonce = new byte[16];
        new SecureRandom().nextBytes(nonce);
        String secKey = Base64.encodeToString(nonce, Base64.NO_WRAP);

        String handshake = "GET /ws HTTP/1.1\r\n" +
                "Host: " + targetHost + ":" + targetPort + "\r\n" +
                "Upgrade: websocket\r\n" +
                "Connection: Upgrade\r\n" +
                "Sec-WebSocket-Key: " + secKey + "\r\n" +
                "Sec-WebSocket-Version: 13\r\n\r\n";

        outStream.write(handshake.getBytes());
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

        String headers = headerBuf.toString();
        if (!headers.contains("101 Switching Protocols")) {
            throw new IllegalStateException("Handshake failed: " + headers);
        }

        isConnected.set(true);
        notifyConnected();
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
                String text = new String(payload, "UTF-8");
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
                    sendText("{\"type\":\"ping\"}");
                } catch (InterruptedException ie) {
                    break;
                } catch (Exception e) {
                    break;
                }
            }
        }, "AeonixWS-Heartbeat");
        heartbeatThread.start();
    }

    public synchronized void sendText(String message) {
        if (!isConnected.get() || outStream == null) return;
        new Thread(() -> {
            try {
                byte[] raw = message.getBytes("UTF-8");
                byte[] frame = encodeClientFrame(0x1, raw);
                synchronized (outStream) {
                    outStream.write(frame);
                    outStream.flush();
                }
            } catch (Exception e) {
                Log.w(TAG, "Error sending frame: " + e.getMessage());
            }
        }).start();
    }

    private void sendPong(byte[] appData) {
        try {
            byte[] frame = encodeClientFrame(0xA, appData);
            synchronized (outStream) {
                outStream.write(frame);
                outStream.flush();
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
        mainHandler.post(listener::onConnected);
    }

    private void notifyDisconnected(String reason) {
        mainHandler.post(() -> listener.onDisconnected(reason));
    }

    private void notifyMessage(String msg) {
        mainHandler.post(() -> listener.onMessage(msg));
    }
}
