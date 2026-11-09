# ÆONIX PRISM RC-1 — Limited English Two-Device Release

ÆONIX PRISM RC-1 is conditionally certified for a local two-device architecture using POCO M4 Pro 5G as the controller and Fire TV Stick Lite as the native display/input terminal.

## What is included
- Local-first controller and storage vault.
- Deterministic Sentinel approval gate on POCO.
- Governed mission lifecycle with verification receipt and replay protection.
- Crash reconciliation for interrupted missions.
- Encrypted local recovery vault and restore drill.
- Native Fire TV Leanback interface with no WebViews.
- English speech-fixture transcription.
- Local burst-mode Qwen inference.
- Passive network observation with fail-closed active-scan boundaries.

## What is deferred
- Spoken Hindi and Hinglish recognition.
- Fire TV remote-microphone push-to-talk.
- External public-data gateways.
- Multi-device mesh routing.
- Conditional smart-home integrations.

## Important limitations
- The physically verified RC-1 artifact is app-debug.apk.
- The release APK was built but not installed or tested.
- Cold-start UI rendering has measured jank.
- Long-duration memory soak is still pending.
- POCO-only backups do not survive physical loss of the phone.
- Loss of the recovery passphrase can make encrypted backups unrecoverable.

## Verification
- 199 tests passed, 0 failed, 0 errors, 0 skipped.
- Test duration: 80.904 seconds.
- Zero integration mocks.
- Production database and secrets remained unchanged.

## Security boundary
POCO is the sole approval authority for consequential actions. Fire TV cannot approve protected operations. Voice approval cannot authorize protected actions.
