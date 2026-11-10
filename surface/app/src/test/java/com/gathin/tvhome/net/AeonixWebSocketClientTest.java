package com.gathin.tvhome.net;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.junit.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.X509TrustManager;

public class AeonixWebSocketClientTest {

    // Valid Sovereign X.509 Certificate (PEM) from POCO Core Mind
    private static final String TEST_CERT_PEM =
        "-----BEGIN CERTIFICATE-----\n" +
        "MIIDdDCCAlygAwIBAgIUdZHiR3el5OYraGa5mq7RS++eIVUwDQYJKoZIhvcNAQEL\n" +
        "BQAwTzELMAkGA1UEBhMCSU4xJDAiBgNVBAoMG0FFT05JWCBQUklTTSBTb3ZlcmVp\n" +
        "Z24gTWluZDEaMBgGA1UEAwwRYWVvbml4LWNvcmUubG9jYWwwHhcNMjYxMDMwMTIz\n" +
        "NjAzWhcNMzYxMDI4MTIzNjAzWjBPMQswCQYDVQQGEwJJTjEkMCIGA1UECgwbQUVP\n" +
        "TklYIFBSSVNNIFNvdmVyZWlnbiBNaW5kMRowGAYDVQQDDBFhZW9uaXgtY29yZS5s\n" +
        "b2NhbDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAKqWNWU5Xw+xnn3e\n" +
        "laISbzF9nmKnXATtMUccYg0kssOu2l/hoiQFEscgrYGHTBsdLueRbbpK1wJ0ExEb\n" +
        "uznr1dVV9jPkYpQfBKO15YXFgIe7H3Qc/7W/5FPe3cELZPhMbsiU+yZhlxtrDXOm\n" +
        "RrPgVAQ68CQd8sCEAChoV6eJ5mZWZeb+9DK7lQXR67UXmd6oFgDooDoyF6r3TJsN\n" +
        "9RFkEK84+Q2nTGf+NXYUjoc2NqsRX+bMD8B3dCgRNhmKqpEaCiNd1BLErYwjydvz\n" +
        "tHdy8L9ZnyGTGOoqjRagMaJqy5THcgxysdOCUERe/arQfXyqPVtMwYo6eb9M3epw\n" +
        "XJT+TCcCAwEAAaNIMEYwMwYDVR0RBCwwKoIJbG9jYWxob3N0ghFhZW9uaXgtY29y\n" +
        "ZS5sb2NhbIcEfwAAAYcECnQXqDAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEB\n" +
        "CwUAA4IBAQB1cRrpKlHOKyHAzpxgp4MHo1IJXCXTGtWWWfvldz+I5WyMMx6NpEEy\n" +
        "lBeyTjcY03557LYlsVRYS7dErCBBDXQM+yI/En8Sm+9+qVsuqE/19NuRW/gfDcY7\n" +
        "SxP10OXVouVV6WBlvbe8LMZjJk6s95UQved+h2DqZhpVr5z6XLvJB/hFSw+5iO4G\n" +
        "6OLRtYvKV17tkb+R2KdQyt7Qq48BSOl5J0KkUjp3XZq8Xgva4wagcC8SKIO25pBf\n" +
        "YwNXVq3EngJRHc1xUtVi/JQsTtQpUTmaKzy7FufNry+/Q7SZ4+tGJa6siHuSh8mG\n" +
        "XZrjsnoQkwe5LthHeW5BEUm2bFITTSdy\n" +
        "-----END CERTIFICATE-----\n";

    @Test
    public void testNullPinThrowsIllegalArgumentException() {
        try {
            AeonixWebSocketClient.createPinnedTrustManager(null);
            fail("Expected IllegalArgumentException for null pin");
        } catch (IllegalArgumentException e) {
            assertEquals("MISSING_PIN: Certificate pin cannot be null or empty. Plaintext fallback prohibited.", e.getMessage());
        }
    }

    @Test
    public void testEmptyPinThrowsIllegalArgumentException() {
        try {
            AeonixWebSocketClient.createPinnedTrustManager("");
            fail("Expected IllegalArgumentException for empty pin");
        } catch (IllegalArgumentException e) {
            assertEquals("MISSING_PIN: Certificate pin cannot be null or empty. Plaintext fallback prohibited.", e.getMessage());
        }
    }

    @Test
    public void testWhitespacePinThrowsIllegalArgumentException() {
        try {
            AeonixWebSocketClient.createPinnedTrustManager("   \t\n");
            fail("Expected IllegalArgumentException for whitespace pin");
        } catch (IllegalArgumentException e) {
            assertEquals("MISSING_PIN: Certificate pin cannot be null or empty. Plaintext fallback prohibited.", e.getMessage());
        }
    }

    @Test
    public void testEmptyCertChainThrowsCertificateException() throws Exception {
        X509TrustManager tm = AeonixWebSocketClient.createPinnedTrustManager("AA:BB:CC:DD");
        try {
            tm.checkServerTrusted(new X509Certificate[0], "RSA");
            fail("Expected CertificateException for empty cert chain");
        } catch (CertificateException e) {
            assertEquals("Empty certificate chain", e.getMessage());
        }
    }

    @Test
    public void testValidPinCreatesTrustManagerAndSocketFactory() throws Exception {
        String dummyPin = "11:22:33:44:55:66:77:88:99:00:AA:BB:CC:DD:EE:FF:11:22:33:44:55:66:77:88:99:00:AA:BB:CC:DD:EE:FF";
        X509TrustManager tm = AeonixWebSocketClient.createPinnedTrustManager(dummyPin);
        assertNotNull(tm);
        assertEquals(0, tm.getAcceptedIssuers().length);

        SSLSocketFactory factory = AeonixWebSocketClient.getPinnedSSLSocketFactory(dummyPin);
        assertNotNull(factory);
    }

    @Test
    public void testMismatchedPinThrowsCertificateException() throws Exception {
        X509TrustManager tm = AeonixWebSocketClient.createPinnedTrustManager(
            "00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF"
        );

        CertificateFactory cf = CertificateFactory.getInstance("X.509");
        X509Certificate cert = (X509Certificate) cf.generateCertificate(
            new ByteArrayInputStream(TEST_CERT_PEM.getBytes(StandardCharsets.UTF_8))
        );
        try {
            tm.checkServerTrusted(new X509Certificate[]{cert}, "RSA");
            fail("Expected CertificateException for mismatched pin");
        } catch (CertificateException e) {
            assertTrue(e.getMessage().contains("Certificate pin mismatch"));
        }
    }

    @Test
    public void testMatchingPinSucceeds() throws Exception {
        CertificateFactory cf = CertificateFactory.getInstance("X.509");
        X509Certificate cert = (X509Certificate) cf.generateCertificate(
            new ByteArrayInputStream(TEST_CERT_PEM.getBytes(StandardCharsets.UTF_8))
        );

        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] der = cert.getEncoded();
        byte[] digest = md.digest(der);
        StringBuilder sb = new StringBuilder();
        for (byte b : digest) {
            sb.append(String.format("%02X", b));
        }
        String actualFp = sb.toString();

        X509TrustManager tm = AeonixWebSocketClient.createPinnedTrustManager(actualFp);

        // Verification must pass cleanly without throwing CertificateException
        tm.checkServerTrusted(new X509Certificate[]{cert}, "RSA");
    }

    @Test
    public void testSensitiveActionsAreRejected() {
        // Sentinel approvals and sensitive commands must be identified as sensitive
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"sentinel_action\",\"request_id\":\"req-123\",\"approved\":true}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"sentinel_approval\",\"approved\":true}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"mission_claim\",\"mission_id\":\"m-456\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"mission_execute\",\"mission_id\":\"m-456\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"file_delete\",\"path\":\"/vault/db.sqlite3\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"wipe\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"destructive_action\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"osint_query\",\"target\":\"domain\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"terminal_cmd\",\"command\":\"rm -rf /\"}"));
        assertTrue(AeonixWebSocketClient.isSensitiveAction("{\"request_id\":\"req-999\",\"approved\":false}"));
    }

    @Test
    public void testNonSensitiveActionsAreAccepted() {
        // UI navigation, focus, ping, and status events must be identified as non-sensitive
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"dpad_nav\",\"keycode\":19,\"timestamp\":1710000000}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"dpad_nav\",\"keycode\":20,\"timestamp\":1710000001}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"ui_state\",\"screen\":\"home\"}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"focus_change\",\"position\":2}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"ping\"}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction("{\"type\":\"status_query\"}"));
        assertFalse(AeonixWebSocketClient.isSensitiveAction(null));
        assertFalse(AeonixWebSocketClient.isSensitiveAction(""));
    }

    @Test
    public void testBoundedQueueCapacityAndDropPolicy() {
        AeonixWebSocketClient client = new AeonixWebSocketClient(null, new AeonixWebSocketClient.Listener() {
            @Override public void onConnected() {}
            @Override public void onDisconnected(String reason) {}
            @Override public void onMessage(String payload) {}
            @Override public void onError(Throwable t) {}
        });

        assertEquals(0, client.getQueueSize());
        assertEquals(0, client.getDroppedEventCount());

        // Queue 60 non-sensitive events while offline
        for (int i = 0; i < 60; i++) {
            client.sendText("{\"type\":\"dpad_nav\",\"seq\":" + i + "}");
        }

        // Bounded ceiling: queue must not exceed MAX_QUEUE_CAPACITY (50)
        assertEquals(50, client.getQueueSize());
        // 10 events must have been dropped (overflow policy: drop oldest)
        assertEquals(10, client.getDroppedEventCount());
    }

    @Test
    public void testSensitiveActionNeverEntersOfflineQueue() {
        AeonixWebSocketClient client = new AeonixWebSocketClient(null, new AeonixWebSocketClient.Listener() {
            @Override public void onConnected() {}
            @Override public void onDisconnected(String reason) {}
            @Override public void onMessage(String payload) {}
            @Override public void onError(Throwable t) {}
        });

        assertEquals(0, client.getQueueSize());

        // Attempt to queue sensitive Sentinel approval while offline
        client.sendText("{\"type\":\"sentinel_action\",\"request_id\":\"req-999\",\"approved\":true}");
        client.sendText("{\"type\":\"mission_claim\",\"mission_id\":\"m-001\"}");
        client.sendText("{\"type\":\"file_delete\",\"path\":\"/important\"}");

        // None of these sensitive actions may enter the offline queue!
        assertEquals(0, client.getQueueSize());
        assertEquals(0, client.getDroppedEventCount());
    }

    @Test
    public void testExponentialBackoffProgressionAndCeiling() {
        int backoff = AeonixWebSocketClient.INITIAL_BACKOFF_MS;
        assertEquals(1000, backoff);

        backoff = (int) Math.min(backoff * AeonixWebSocketClient.BACKOFF_MULTIPLIER, AeonixWebSocketClient.MAX_BACKOFF_MS);
        assertEquals(2000, backoff);

        backoff = (int) Math.min(backoff * AeonixWebSocketClient.BACKOFF_MULTIPLIER, AeonixWebSocketClient.MAX_BACKOFF_MS);
        assertEquals(4000, backoff);

        backoff = (int) Math.min(backoff * AeonixWebSocketClient.BACKOFF_MULTIPLIER, AeonixWebSocketClient.MAX_BACKOFF_MS);
        assertEquals(8000, backoff);

        backoff = (int) Math.min(backoff * AeonixWebSocketClient.BACKOFF_MULTIPLIER, AeonixWebSocketClient.MAX_BACKOFF_MS);
        assertEquals(16000, backoff);

        // Ceiling test: next backoff remains clamped at MAX_BACKOFF_MS (16000)
        backoff = (int) Math.min(backoff * AeonixWebSocketClient.BACKOFF_MULTIPLIER, AeonixWebSocketClient.MAX_BACKOFF_MS);
        assertEquals(16000, backoff);
    }
}
