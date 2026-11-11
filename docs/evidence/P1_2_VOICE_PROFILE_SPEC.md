# ÆONIX PRISM: P1-2 Voice Profile Specification & Evidence Ledger

## 1. Executive Summary & Status
- **Candidate Voice:** `en_IN-spicor-medium`
- **Status:** `APPROVED_PRIMARY_EVALUATION`
- **Production Readiness:** **NOT YET FINALIZED**
- **Distribution Scope:** **LOCAL PRIVATE RESEARCH / EVALUATION ONLY**
- **Approved Pacing Profile:** `speed = 0.90`, `silence_scale = 0.20`, `noise_scale = 0.667`, `noise_scale_w = 0.800`

---

## 2. What Was Proven
1. **Audible In-App Fire TV Playback:**
   - Physical execution through the authenticated, certificate-pinned Sovereign TLS WebSocket path.
   - Fire TV client (`com.aether.launcher`) successfully initialized Android `AudioTrack` (`USAGE_MEDIA`, `CONTENT_TYPE_MUSIC`), wrote all PCM frames, and drained playback cleanly without underrun.
2. **Human Auditory Approval on Hardware:**
   - **Test A (*"Hello, Aadi."*):** Approved by human listener (*"It was good."*).
   - **Test B (*"The phone and television are connected."*):** Approved by human listener (*"The second audio was good."*).
   - **Test C (*"Please pause, then continue."*):** Approved by human listener (*"It was good."*).
3. **Pronunciation Verdict:**
   - Aadi pronunciation accepted by human listener under the 0.90x cadence.
4. **Mechanical Packaging Compatibility:**
   - Upstream raw Piper model adapted to `sherpa-onnx 2.0.1` by injecting the 7 required metadata key-value pairs into the ONNX protobuf header without altering model weights.
   - 100% token symbol coverage verified across all test phrases against mechanically extracted `tokens.txt` (161 symbols).

---

## 3. What Was NOT Proven
- **No Acoustic Bit-for-Bit Claims:** The tests prove successful `AudioTrack` playback and human audibility; they do **not** prove absence of Android-side OS resampling or format conversion.
- **No Phonetic Micromanagement Claims:** Listening approval proves perceptual acceptance by a human listener; it does **not** assert bit-level formant accuracy or specific phonetic features (e.g. pure dental stops vs alveolar transitions).
- **Production Finality:** This milestone does not finalize the model for production or binary distribution.

---

## 4. Legal, Licensing & Governance Boundaries
- **Model Wrapper License (AGPL-3.0):**
  - Released by NavGurukul AI Labs under GNU Affero General Public License v3.0.
  - Network-triggered services utilizing AGPL assets require complete corresponding source code disclosure.
- **Dataset Provenance (IISc SPICOR English TTS Corpus):**
  - Audio dataset collected by the Signal Processing Interpretation and Representation (SPIRE) Lab at the Department of Electrical Engineering, Indian Institute of Science (IISc Bangalore).
  - Governed by SPIRE Datasets Terms of Use requiring research/project request clearance and prohibiting commercial redistribution.
- **Evaluation-Only Classification:**
  - This candidate profile is strictly bounded to internal private research.
  - A permissively licensed voice (or formally cleared commercial license) must be secured prior to any public binary release.

---

## 5. Fire TV Transport Boundary
- **Transport Verdict:** PASS — authenticated, certificate-pinned WebSocket delivery; `AudioTrack` initialized; playback completed; human reported audible speech.
- **Control Contract:** Single `voice_audio_start` control message, bounded 4096-byte raw PCM binary chunks (`pcm_s16le`, 22050 Hz, mono), and single `voice_audio_complete` control frame.
- **Guards:** 5 MB ceiling, 15-second TTL validation, single-use per connection test trigger, immediate server teardown.

---

## 6. Future Multi-Agent Voice Identity Registry Direction
PRISM will eventually support distinct voice identities for different sovereign AI agents:
- **PRISM:** Primary Indian English voice (`en_IN-spicor-medium` / future permissive equivalent).
- **Sentinel:** Diagnostic and security voice.
- **Lumina / Atlas:** Task-specific and ambient personas.

Each entry in the future Voice Identity Registry will declaratively specify:
- Model ID, upstream git commit hash, and ONNX SHA-256.
- Speaker ID (for multi-speaker checkpoints).
- Dialect/accent metadata.
- Calibrated cadence parameters (`speed`, `silence_scale`, `noise_scale`).
- Lexicon / pronunciation overrides.
- Qualified baseline fallback voice (`vits-piper-en_US-ljspeech-medium`).
- Strict audit and approval status.
