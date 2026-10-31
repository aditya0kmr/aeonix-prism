# Architecture Decision Record (ADR) 0001: Adoption of Reconciled Master Engineering Specification v4.0

* **Status:** Adopted
* **Date:** 2026-10-31
* **Deciders:** Sovereign Operator (Aadi) & Core Architecture Agent
* **Canonical Gate Statuses:**
  * **Gate G0 (Audit & Recovery Baseline):** **PARTIAL** (Disaster recovery verified, active baseline established, multi-device release verification in progress)
  * **Gate G1 (Authority Foundation):** **OPEN** (Authority foundation hardened, negative security suites verified, active vault encryption migration deferred pending formal G1 sign-off)

---

## 1. Governing Specification Baseline & Cryptographic Manifest

The portable baseline documents have been incorporated into the repository under `docs/baseline/`. Their canonical cryptographic SHA-256 fingerprints are recorded below:

| Baseline Document | Repository Relative Path | Canonical SHA-256 Hash | Description |
|---|---|---|---|
| Master Engineering Specification | [`docs/baseline/AEONIX_PRISM_Reconciled_Master_Engineering_v4.md`](../baseline/AEONIX_PRISM_Reconciled_Master_Engineering_v4.md) | `c8d465c5c83bae2e4edb439dbd20e31e47cdfa0cdd87d05874fb2e19082b66d6` | Reconciled Master Engineering Specification v4.0 |
| Requirements Seed Catalog | [`docs/baseline/AEONIX_PRISM_Requirements_Seed.csv`](../baseline/AEONIX_PRISM_Requirements_Seed.csv) | `a6122b62956b4256e49faa3b9697b5966308ec6cb9e6450b624812ce49d6c600` | 427 requirement seeds across 54 capability owners |
| Engineering Guide | [`docs/baseline/AEONIX_PRISM_START_HERE.md`](../baseline/AEONIX_PRISM_START_HERE.md) | `e7fcf64237dcfefeb324112865b4b9fbb16780cd285ba7e9807d11d4f93ae463` | Agent onboarding guide & operational constraints |
| Source Manifest | [`docs/baseline/source_manifest.csv`](../baseline/source_manifest.csv) | `5dee6307d00c1a6acd6a60af87fb77d7512965cc799109d8e5ef7ad7ba2023d0` | 18 ancestral artifacts catalog from Google Drive |

---

## 2. Context and Problem Statement

The project originated across 18 separate design documents and conversational blueprints in Google Drive (`1ARRSEmUAE1lw3ubuBspiPEg35BeBsa-N`). Over time, these documents introduced competing architectural assumptions:
* Approval flows in early diagrams depicted approvals granted directly via the Fire TV remote, contradicting the sovereign root-of-trust security model.
* Voice transport was variously specified as Opus, WebRTC, or raw PCM.
* Process models varied between heavyweight multi-process LangGraph/CrewAI frameworks and bounded async single-process execution.
* Memory ceilings varied between 80MB, 150MB, 180MB, and 250MB.
* Nomenclature varied across ancestral names (AURA, KAIROS, OMNIA, NOEMA, AETHERION).

The newly provided `AEONIX_PRISM_Agent_Implementation_Packet_v4.zip` establishes a formal, unified, evidence-based engineering baseline (v4.0).

---

## 3. Decision Register (D01 – D18)

We formally adopt the 18 governing decisions established in Section 2 of Specification v4.0:

1. **D01 (Device Topology):** Strict two-device architecture (POCO M4 Pro 5G as Sovereign Core Mind $\longleftrightarrow$ Fire TV Stick Lite as Living-Room Glass Terminal). No third compute host is required.
2. **D02 (Evidence Boundary):** Claims require verifiable empirical evidence. Test counts or passing suites do not equate to full requirement satisfaction. Unmeasured hypotheses remain labeled hypotheses.
3. **D03 (Privacy Modes):** Three formal operating modes: `STRICT_OFFLINE` (WAN blocked), `LOCAL_BASE` (default; local Qwen/Whisper with zero telemetry), and `HYBRID_OPT_IN` (explicit operator-approved external queries).
4. **D04 (Cost & Quotas):** Zero paid cloud inference required for base operation. Optional cloud adapters operate under strict daily quotas with paid fallback disabled.
5. **D05 (Approval Authority):** Consequential execution is approved manually and strictly from the authenticated POCO operator interface. The Fire TV terminal may display, dismiss, cancel, or deny (`DENY / CANCEL (SAFE)`), but **cannot approve**.
6. **D06 (Adaptive Consent / AXIOM):** Trust learning records frequency and patterns to *recommend* scope grants. Past approval frequency **never silently creates permissions**. R4/R5 actions remain per-action manual.
7. **D07 (Local Models):** Single active local generation slot on POCO (Qwen 2.5 0.5B GGUF via `llama-server`). Default memory policy is burst-unload; residency requires measured headroom. Named agents represent logical execution roles, not separate resident model weights.
8. **D08 (Voice Transport):** Push-To-Talk (PTT) baseline using **16-bit 16kHz Mono PCM** over WebSocket directly to POCO. No continuous always-on TV microphone listening.
9. **D09 (Fast Streaming Feedback):** Quick acoustic receipt feedback; never speak a success claim before physical verification, and never stream unverified policy decisions.
10. **D10 (Native Leanback UI):** Pure native Android Jetpack Leanback UI (Java/Kotlin). **Zero WebViews**. Proposed project memory ceilings: $<80\text{MB}$ active PSS ambient/screensaver, $<180\text{MB}$ peak full-use, APK $<100\text{MB}$.
11. **D11 (Thin Client Compliance):** Fire TV runs zero heavy inference, zero background network scanning, and maintains **0 KB SQLite** database memory. POCO master secrets never touch the TV.
12. **D12 (Active Storage Encryption):** Encrypted backup archives do not constitute active memory encryption. Sensitive active vault content and secrets require field-level authenticated AES-256-GCM encryption.
13. **D13 (Sandboxed Tools & Forge):** Termux UID and PRoot are not secure multi-tenant isolation boundaries. Generated code must never execute in Core under Core credentials. Execution relies on allowlisted, typed tool catalogs (`shell=False`, argument grammar validation, path containment).
14. **D14 (ASGI Orchestrator):** Single bounded async Python orchestrator on POCO Termux. Bounded thread pool executors for heavy tasks. No Redis or distributed consensus unless proven necessary.
15. **D15 (Discovery vs. Authentication):** mDNS discovers connection endpoints but provides zero security. Handshakes require cryptographic HMAC-SHA256 bearer tokens. Hardcoded IPs do not define authority.
16. **D16 (Safety Boundaries):** Legitimate personal assistant and defensive OSINT ambition; zero unauthorized intrusion, covert recording, or private account bypassing.
17. **D17 (Nomenclature & Register):** 54 capability owners registered in Section 26. Ancestral codenames map into current modules (e.g., NOEMA owns memory, LUMEN owns display context, SPECTRA owns media/IPTV).
18. **D18 (G0–G12 Gates):** Structured progression through canonical gates:
    * G0: Audit/Recovery Baseline (PARTIAL)
    * G1: Authority Foundation (OPEN)
    * G2: Durable Core & Active Encrypted Memory
    * G3: PRISM UI Vertical Slice
    * G4: VOX Baseline
    * G5: NOVA Local LLM & Optional Hybrid Gateway
    * G6: AADYA Context & Personal Memory
    * G7: Research / OSINT Pipeline
    * G8: Visual & Forensic Cases
    * G9: Guardian & LAN Supervision
    * G10: Forge Sandboxed Workflows
    * G11: Advanced Capabilities
    * G12: Release Acceptance

---

## 4. Superseded Legacy Instructions

This ADR explicitly records that the following older document instructions are superseded:
1. **Fire TV Remote Approval:** Any flow showing remote approval of consequential actions is superseded by D05 (manual POCO operator approval only).
2. **Opus Audio Compression:** Superseded by D08 (16-bit 16kHz Mono PCM baseline).
3. **Hardware Memory Budgets:** Older references to 250MB or 150MB TV budgets are superseded by D10 ($<80\text{MB}$ ambient, $<180\text{MB}$ peak).
4. **Multi-Process Swarms:** LangGraph/CrewAI multi-process designs are superseded by D14 (single async orchestrator with heavy executor thread pools) to stay within Termux process killer budgets.
5. **Hardware Security Assumptions:** Termux UID PIN challenges are recognized as interim application access control against accidental use, not hardware-backed multi-user sandbox boundaries.
