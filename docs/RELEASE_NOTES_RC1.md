# ÆONIX PRISM RC-1 Release Notes

## Release verdict
CONDITIONALLY CERTIFIED FOR RELEASE CANDIDATE 1 (RC-1)

## Scope
- Two-device local-first architecture.
- POCO M4 Pro 5G is controller, storage vault, intelligence host, and sole approval authority.
- Fire TV Stick Lite is a native display/input terminal.
- No cloud AI dependency and no third compute host.
- English speech-fixture validation.
- Deterministic Sentinel authorization on POCO.
- Governed mission lifecycle with verification receipt and replay protection.
- Encrypted local recovery vault.
- Native Leanback Fire TV UI with no WebViews.

## Certified artifact
- Installed and physically verified APK: app-debug.apk
- APK SHA-256: cd7b883f6640f0d1fbe90a42e90899194e9fb2195eec98036d8ca4474eac5483
- Package: com.aether.launcher
- Version: 2.0-hybrid
- versionCode: 20

## Not certified
- Universal offline autonomous operations.
- Spoken Hindi or Hinglish recognition.
- Fire TV remote-microphone push-to-talk.
- External public-data gateways.
- Multi-device mesh routing.
- Unconstrained autonomous execution.
- Release APK deployment.

## Known limitations
- Cold-start UI layout inflation jank: 20 of 26 initial frames missed the 16.6 ms display deadline; 9 missed VSYNCs during startup.
- Current stability evidence does not establish multi-hour or multi-day leak immunity.
- POCO-only backup does not protect against physical loss of the phone.
- Loss of the operator recovery passphrase can make encrypted backups permanently unrecoverable.
- Voice approval cannot authorize protected actions.

## Verification
- Portable suite: 199 PASS / 0 FAIL / 0 ERROR in 80.904 seconds.
- Zero integration mocks.
- Production database and secrets remained unchanged during the test run.
- Evidence manifest: 50 files verified successfully.

## Local tag
- rc1-limited-english exists locally.
- It points to commit d765d2b3a1922834396fa961fe808da7e4474428.
- It has not been pushed to origin.
