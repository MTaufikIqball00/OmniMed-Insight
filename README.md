# OmniMed Insight (XAI)

<p align="center">
  <strong>Multimodal Clinical Decision-Support, Explainable Medical AI (Grad-CAM), Evidence-Grounded Report Drafting & HL7 FHIR R4 Interoperability Platform</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-1.75%2B-orange?logo=rust" alt="Rust" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/Next.js-14.2%20App%20Router-black?logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/TailwindCSS-v3.4-38bdf8?logo=tailwind-css" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/Interoperability-HL7%20FHIR%20R4-firebrick" alt="HL7 FHIR R4" />
  <img src="https://img.shields.io/badge/Security-Argon2id%20%7C%20CSRF%20%7C%20IDOR%20Guard-success" alt="Security" />
  <img src="https://img.shields.io/badge/Status-Fully%20Tested-emerald" alt="Status" />
</p>

---

> [!IMPORTANT]
> ### ⚠️ Mandatory Clinical Safety & Regulatory Notice
> **OmniMed Insight (XAI) is an assistive clinical decision-support software platform developed exclusively for qualified healthcare professionals using synthetic test data.**
> - It is **not** an FDA 510(k), CE-marked, or PMDA-cleared medical device.
> - It must **never** be used for autonomous clinical diagnosis or treatment planning.
> - All deep learning inferences, uncertainty metrics, Grad-CAM attribution heatmaps, and evidence-grounded report drafts are auxiliary decision aids that **mandatorily require independent verification and signed clinical attestation by an authorized clinician.**

---

## 📑 Table of Contents
- [📸 Platform Screenshots](#-platform-screenshots)
- [1. System Architecture](#1-system-architecture)
- [2. Key Capabilities & Technical Highlights](#2-key-capabilities--technical-highlights)
- [3. Port Allocation & Network Topology](#3-port-allocation--network-topology)
- [4. Repository Structure](#4-repository-structure)
- [5. Quick Start (Windows / macOS / Linux)](#5-quick-start-windows--macos--linux)
- [6. Demo Accounts & RBAC Matrix](#6-demo-accounts--rbac-matrix)
- [7. Step-by-Step Clinical Workflow Guide](#7-step-by-step-clinical-workflow-guide)
- [8. Automated Testing & Verification](#8-automated-testing--verification)
- [9. Data Governance & Security Disclosures](#9-data-governance--security-disclosures)

---

## 📸 Platform Screenshots

### 1. Interactive Medical Image Viewer & PyTorch Grad-CAM XAI Workspace
> *Interactive radiology canvas with pan, zoom (75%–300%), LUT invert, dynamic Grad-CAM opacity blending slider (65%), thermal activation scale legend, Shannon entropy uncertainty metrics, and anatomical quadrant attributions.*

<p align="center">
  <img src="docs/image/OmniMed.png" alt="Medical Image Viewer and Grad-CAM XAI Workspace" width="100%" />
</p>

---

### 2. Evidence-Grounded Report Drafting, Version History & Clinician Attestation
> *Synthesized 5-part radiology report draft with version history tracking (`v1 APPROVED`), clinician context notes integration, evidence provenance chain citations, and signed clinical attestation.*

<p align="center">
  <img src="docs/image/OmniMed2.png" alt="Evidence-Grounded Report Drafting and Clinician Sign-Off" width="100%" />
</p>

---

### 3. HL7 FHIR R4 (v4.0.1) Interoperability & Bundle Validation
> *Automated structural and terminology validation generating verified HL7 FHIR R4 JSON bundles containing `Patient`, `Practitioner`, `Encounter`, `Observation`, `ImagingStudy`, and `DiagnosticReport` resources with `HTEST` synthetic security tags.*

<p align="center">
  <img src="docs/image/OmniMed3.png" alt="HL7 FHIR R4 Interoperability and Bundle Validator" width="100%" />
</p>

---

## 1. System Architecture

OmniMed Insight enforces strict architectural boundaries: **Rust** serves as the primary security gateway, session custodian, and regulatory audit boundary, while **Python** executes hardware-calibrated vision inference and gradient-based XAI hooks. The **Next.js** frontend provides a responsive, accessible clinical workspace.

```mermaid
flowchart TD
    subgraph Client["Healthcare Professional Client (Browser)"]
        UI["Next.js 14 App Router + Tailwind CSS v3\nPort: 3100\n- Medical Image Viewer (Pan, Zoom, LUT)\n- Grad-CAM Heatmap Opacity Slider\n- Report Version History & Editor\n- Patient Registry & Case Management\n- ICU Early Warning & Sepsis Dashboard (6-12h Horizon)"]
    end

    subgraph SecurityBoundary["Primary Application Backend & Security Boundary (Rust)"]
        Axum["Axum 0.7 REST API Server\nPort: 8100\n- Argon2id Password Hashing\n- HttpOnly Session Cookies + Anti-CSRF Token\n- Server-Side RBAC & IDOR Guard (patient_assignments)\n- Immutable Security Audit Trail\n- HL7 FHIR R4 Validator & Bundle Exporter\n- ICU Stays, Longitudinal Vitals & Alert Deduplication Engine"]
        DB[("SQLx Storage Layer\nDefault: SQLite (./data/omnimed.db)\nConfigurable: PostgreSQL :5433")]
        Storage[("./data/storage/\n- Uploads (Original Image + SHA-256)\n- Overlays (Grad-CAM RGBA Artifcats)")]
        Axum --> DB
        Axum --> Storage
    end

    subgraph AIService["Isolated Medical AI & Explainability Engine (Python)"]
        FastAPI["FastAPI Inference Engine\nPort: 8200\n- Magic-Byte Binary Header Validator\n- PyTorch DenseNet-121 Vision Model\n- Real Grad-CAM Hooks (features.denseblock4)\n- Patch Occlusion & Shannon Uncertainty\n- LightGBM ICU Sepsis-3 Early Warning (6-12h Horizon)\n- Tree SHAP Feature Attribution Engine"]
    end

    subgraph Interop["Interoperability Layer (Optional)"]
        FHIRServer["HL7 FHIR R4 Test Server\nPort: 8300\n(Patient, Practitioner, Encounter,\nObservation, DiagnosticReport)"]
    end

    UI -->|HTTPS / Session Cookie + CSRF| Axum
    Axum -->|Internal Mutual Token\nX-Internal-Service-Token| FastAPI
    Axum -.->|Export Bundle| FHIRServer
```

---

## 2. Key Capabilities & Technical Highlights

### 🔬 Explainable AI (XAI), Checkpoint Integrity & PyTorch Vision Engine
* **Real Gradient-Weighted Class Activation Mapping (Grad-CAM / HiResCAM)**: Forward and backward gradient hooks registered on `features.denseblock4` of PyTorch DenseNet-121 to extract real spatial feature sensitivities with transparent low-activation masking (`alpha = 0`) and no mock approximations.
* **Reproducible Training, Checkpoint Integrity & Post-Hoc Calibration (`ai-service-python/imaging_pipeline/`)**:
  * Supports `--manifest-csv` (patient-level 70/15/15 stratified splits for DUA-authorized clinical cohorts) and `--synthetic-benchmark` (`SYNTHETIC_BENCHMARK_FIXTURE`, 240 patients / 480 4-class CXR images, zero patient overlap verified).
  * Validates `MODEL_WEIGHTS_PATH` + `MODEL_WEIGHTS_EXPECTED_SHA256`, finite weights, and bounded forward logits (`|logit| < 100.0`), rolling back safely to `RESEARCH_UNVERIFIED` on any corruption or mismatch.
  * Fits `TemperatureScaler` (`T = 0.4780`) and `MulticlassPlattScaler` strictly on `val_logits.npz` (`n = 72`), achieving held-out synthetic benchmark `Accuracy = 0.9722`, `ECE = 0.0216`, `Brier = 0.0113`, `NLL = 0.0981` (`CALIBRATED_CHECKPOINT` tagged `SYNTHETIC_BENCHMARK_FIXTURE`). See [`docs/IMAGING_MODEL_PROVENANCE.md`](docs/IMAGING_MODEL_PROVENANCE.md) for external dataset DUA gaps (NIH ChestX-ray14, CheXpert, MIMIC-CXR, RSNA, BraTS not present locally).
* **Predictive Uncertainty Classification**: Evaluates candidate class probabilities using **Shannon Entropy** ($H = -\sum p_i \log_2 p_i$) and surfaces live empirical calibration curves (`ReliabilityBin`) in the UI.

### 🛡️ Rust Application Security & Zero-Trust Architecture
* **Strict Server-Side RBAC**: Role-based access control enforced on every endpoint (`admin`, `clinician`, `reviewer`, `readonly`). Client-side state is never trusted.
* **Cross-Patient IDOR Prevention**: Care team assignments (`patient_assignments`) strictly restrict clinicians to their authorized patients. Unassigned access triggers `403 Forbidden` and records a security incident in `audit_logs`.
* **State-of-the-Art Cryptography**: Passwords salted and hashed with **Argon2id**. Sessions managed via randomized 256-bit cryptographically secure tokens in `SameSite=Lax` HttpOnly cookies paired with anti-CSRF headers.
* **Lossless Image Integrity**: Validates binary magic signatures (PNG, JPEG, TIFF), calculates SHA-256 digests upon upload, and stores original images unaltered.

### 📋 Evidence-Grounded Report Drafting & Clinician Sign-Off
* **5-Part Standard Radiology Structure**:
  1. *Sourced Clinical Facts & LOINC Observations* (Demographics, vitals, labs, and clinician context notes).
  2. *Configured Model Prediction Output & Uncertainty* (DenseNet-121 top scores, calibration status).
  3. *Grad-CAM Spatial Attribution Interpretation* (Activation quadrant, coverage ratio, gradient notice).
  4. *Clinician Impression & Decision-Support Narrative* (Editable synthesized clinical impression).
  5. *Mandatory Limitations & Safety Disclosures* (Non-autonomous clearance warning).
* **Multi-Version History**: Iterative draft versioning (`v1`, `v2`, `v3`...) with immediate selector and status locks (`APPROVED`, `REJECTED`, `DRAFT_PENDING_REVIEW`).

### 🌐 Dynamic Patient & Imaging Case Management
* **Live Patient Registration**: Register new synthetic patients directly from the UI with automated `SYNTH-MRN` generation, FHIR Patient ID mapping, and automated clinician assignment.
* **On-Demand Case Creation**: Open new CXR (Chest Radiograph) or Brain MRI cases linked to any registered patient with custom priorities (`ROUTINE`, `URGENT`, `STAT`).

### ⚡ ICU Early Warning & Sepsis Deterioration Prediction (6–12h Horizon)
* **Expanded PhysioNet 2019 Longitudinal Clinical Cohort (`v2.0.0-physionet2019`, CC BY 4.0)**: Expanded from 118 stays (`4,615` rows) to **988 eligible real ICU stays (`38,270` hourly records)** across Hospital Systems A (`492`) and B (`496`) with **59 sepsis-positive stays / 407 positive 6–12h rows** and zero patient overlap across 70/15/15 stratified splits (`691` train / `148` val / `149` test stays; see [`docs/ICU_DATASET_PROVENANCE.md`](docs/ICU_DATASET_PROVENANCE.md)).
* **Monotonic Clinical Guard & Post-Hoc Isotonic Calibration**: LightGBM (`lightgbm_monotonic`) enforces `monotone_constraints_method="advanced"` (`+1` on Lactate, Shock Index, MAP hypoperfusion depth, qSOFA, HR, Resp, Temp deviation, Creatinine, BUN; `-1` on MAP, SBP, O2Sat, Platelets, HCO3) and validation-fitted `ISOTONIC_CALIBRATION` (`calibrated_threshold = 0.0200`), reducing held-out test ECE from `0.0512` (old 118-stay baseline) to **`0.0005`** while lifting specificity from `56.4%` to **`75.0%`** (`AUROC = 0.7817`, `Sensitivity = 65.1%`, `Brier = 0.0108`).
* **Archive2 5,000-Patient Multi-Center Synthetic Cohort (`v2.0.0-archive2-5k`)**: Audited for strict anti-leakage (excluding post-event interventions, future outcomes, and synthetic target proxies), evaluating 83 predictors with validation-fitted `PLATT_SCALING` (`AUROC = 0.9954`, `AUPRC = 0.9864`, `ECE = 0.0104` vs `0.0225` uncalibrated, `Sensitivity = 92.0%`, `Specificity = 99.5%`, `calibrated_threshold = 0.67`) alongside a Secondary CHF Endpoint (`AUROC = 0.7176`).
* **Sepsis-3 Horizon Modeling & Stratified Tree SHAP**: Targets a **6 to 12-hour warning horizon** ($t_{sepsis}-12 \le t \le t_{sepsis}-6$) using backward-looking observations only and a 200-row stratified `TreeExplainer` background (`INCREASES_RISK` vs `DECREASES_RISK`) guaranteed immune to Lactate/MAP polarity inversion.
* **Alert Deduplication & Signed Clinician Sign-Off**: Stratifies risk (`CRITICAL`, `HIGH`, `MODERATE`, `LOW`, `INSUFFICIENT_DATA`), suppresses repeated alerts with a 4-hour cooldown window, and requires signed clinician acknowledgement notes permanently logged in `audit_logs`.

#### Experimental Comparison (Before vs. After Calibration & Cohort Expansion)

| Module & Model | Cohort / Split | AUROC / Acc | Brier | ECE | Sensitivity / Specificity | Guard / Provenance |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **ICU Primary (Before: 118 stays, Uncalibrated)** | PhysioNet Test (`782` rows) | `0.8663` AUROC | `0.0232` | `0.0512` | `100.0%` / `56.4%` | Unconstrained (Lactate SHAP inversion) |
| **ICU Primary (After: 988 stays, Monotonic + `ISOTONIC_CALIBRATION`)** | PhysioNet Test (`5,625` rows) | `0.7817` AUROC | `0.0108` | **`0.0005`** | `65.1%` / **`75.0%`** | **`Monotonic Clinical Guard: ACTIVE`** |
| **ICU Archive2 Cohort (Before -> After `PLATT_SCALING`)** | Archive2 Test (`750` patients) | `0.9954` AUROC | `0.0111 -> 0.0116` | `0.0225 ->` **`0.0104`** | `92.0%` / `99.5%` | Synthetic tabular cohort (`monotone=False`) |
| **Imaging DenseNet-121 (Before -> After `TEMPERATURE_SCALING`)** | Synthetic Benchmark Test (`72` imgs) | `97.22%` Acc | `0.0085 -> 0.0113` | `0.0190 ->` **`0.0216`** | N/A (4-class) | `SYNTHETIC_BENCHMARK_FIXTURE` (not clinical) |

### 🏥 HL7 FHIR R4 Interoperability
* Generates validated FHIR R4 JSON Bundles encapsulating `Patient`, `Practitioner`, `Encounter`, `Observation` (LOINC-coded vitals and labs), `ImagingStudy`, and `DiagnosticReport` resources.

---

## 3. Port Allocation & Network Topology

All services are configured centrally via `.env` (derived from `.env.example`) and bind strictly to `127.0.0.1` (`localhost`):

| Service | Port | Protocol | Description |
| :--- | :---: | :--- | :--- |
| **Frontend UI** | `3100` | HTTP | Next.js 14 Web Workspace & Diagnostic Viewer |
| **Primary Backend** | `8100` | HTTP | Rust Axum API, Auth, Security Boundary, FHIR Validator |
| **Python AI Engine** | `8200` | HTTP | Internal PyTorch DenseNet-121 + Grad-CAM + LightGBM ICU Engine |
| **FHIR Test Server** | `8300` | HTTP | Optional external HL7 FHIR R4 endpoint |
| **PostgreSQL** | `5433` | TCP | Optional containerized database (SQLite is local default) |

---

## 4. Repository Structure

```text
OmniMed Insight/
├── backend-rust/                  # Primary Rust Backend
│   ├── Cargo.toml                 # Axum, Tokio, SQLx, Argon2 dependencies
│   ├── migrations/                # SQLx database schema migrations
│   │   ├── 0001_initial_schema.sql
│   │   └── 0002_icu_early_warning_schema.sql
│   ├── src/
│   │   ├── audit.rs               # Immutable audit logging engine
│   │   ├── auth.rs                # Argon2id, session cookies, IDOR checks
│   │   ├── config.rs              # App configuration & .env parser
│   │   ├── db.rs                  # Connection pool & synthetic data seeder
│   │   ├── error.rs               # Unified API error types
│   │   ├── models.rs              # Typed domain models & DTOs
│   │   ├── routes.rs              # Endpoint handlers & business logic
│   │   ├── lib.rs                 # Router composition & CORS policy
│   │   └── main.rs                # Axum listener entrypoint
│   └── tests/                     # Integration and security test suite
├── ai-service-python/             # Python Medical AI & XAI Engine
│   ├── app/
│   │   ├── calibration.py         # ECE/Brier/NLL, TemperatureScaler, MulticlassPlattScaler, FrozenEstimator calibrators
│   │   ├── config.py              # Environment configuration & token validator
│   │   ├── imaging.py             # Binary magic-byte & SHA-256 verification
│   │   ├── xai_engine.py          # PyTorch DenseNet-121, checkpoint validation & HiResCAM/Grad-CAM hooks
│   │   ├── icu_engine.py          # Calibrated LightGBM Sepsis-3 & Tree SHAP inference engine
│   │   └── main.py                # FastAPI endpoints & live calibration health checks
│   ├── imaging_pipeline/          # Reproducible DenseNet-121 training, patient-level split & calibration
│   ├── icu_pipeline/              # Reproducible ICU feature engineering, monotonic LightGBM & calibration
│   ├── models/                    # Serialized imaging & ICU artifacts, calibrators, and JSON metadata
│   ├── tests/                     # Pytest suite for imaging, calibration, monotonic SHAP & ICU inference
│   └── requirements.txt           # PyTorch, LightGBM, XGBoost, SHAP, FastAPI
├── frontend/                      # Next.js 14 + Tailwind CSS Frontend
│   ├── package.json               # Next.js 14.2, Tailwind v3, Lucide icons
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx         # Root layout & third-party error boundary
│   │   │   ├── page.tsx           # Multimodal clinical workspace (6 Tabs)
│   │   │   └── globals.css        # Tailwind directives & medical utility styles
│   │   └── components/
│   │       ├── MedicalImageViewer.tsx       # Interactive canvas viewer (LUT, Zoom, Pan)
│   │       └── IcuEarlyWarningWorkspace.tsx # Longitudinal ICU vitals, SHAP & alert console
│   └── __tests__/                 # Frontend contract & contract tests
├── data/                          # Local application state (gitignored)
│   ├── omnimed.db                 # SQLite relational database
│   └── storage/                   # Uploaded scans & derived Grad-CAM overlays
├── docs/                          # Architectural documentation & clinical reports
│   ├── ARCHITECTURE.md            # Comprehensive threat model & specs
│   ├── ICU_DATASET_AND_LABEL_SPEC.md # Sepsis-3 6-12h horizon & cohort provenance
│   ├── ICU_DATASET_PROVENANCE.md  # Expanded 988-stay PhysioNet cohort provenance & splits
│   ├── IMAGING_MODEL_PROVENANCE.md # External radiology dataset DUA audit & synthetic benchmark spec
│   ├── ARCHIVE2_DATASET_REPORT.md # 5,000-patient synthetic cohort & anti-leakage audit
│   ├── XAI_AUDIT_AND_IMPROVEMENT_REPORT.md # XAI calibration, Grad-CAM/SHAP & UX audit
│   └── UI_AUDIT.md                # Accessibility & Tailwind v3 checklist
├── run-local.bat                  # One-click Windows Batch launcher
├── run-local.ps1                  # PowerShell launcher with port conflict detection
├── run-local.sh                   # Linux/macOS Bash companion launcher
├── .env.example                   # Environment configuration template
└── README.md                      # Project documentation
```

---

## 5. Quick Start (Windows / macOS / Linux)

### Prerequisites
* **Rust**: `1.75+` (`cargo` and `rustc`)
* **Python**: `3.10+` with `pip`
* **Node.js**: `18+` or `20+` with `npm`

### Method 1: One-Click Launcher (Recommended)

#### On Windows:
Double-click `run-local.bat`, or run via PowerShell:
```powershell
# Preflight check (verifies ports, runtimes, and hides secrets)
powershell -ExecutionPolicy Bypass -File .\run-local.ps1 -CheckOnly

# Start all services with automated health verification:
powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```

#### On Linux / macOS:
```bash
chmod +x ./run-local.sh
./run-local.sh
```

The launcher will:
1. Verify required runtimes (`rustc`, `python`, `node`).
2. Scan for port conflicts on `3100`, `8100`, `8200`, and `8300`.
3. Auto-generate `.env` with secure 256-bit secrets if not present.
4. Start the Python AI service (`:8200`), Rust backend (`:8100`), and Next.js frontend (`:3100`) in controlled sequence.
5. Poll real `/health` endpoints and display an operational dashboard.

Once running, access the workspace at **[http://127.0.0.1:3100](http://127.0.0.1:3100)**.

---

## 6. Demo Accounts & RBAC Matrix

The local development seed provides pre-configured role accounts to test access control and IDOR protections:

| Role | Email | Password | Assigned Permissions |
| :--- | :--- | :--- | :--- |
| **Clinician** | `clinician@omnimed-insight.local` | `Clinician!2026` | Register patients, open cases, upload scans, run Grad-CAM XAI, trigger ICU Sepsis-3 predictions, acknowledge ICU alerts, author/edit drafts. Assigned to `pat-synth-001` and `pat-synth-002`. |
| **System Admin** | `admin@omnimed-insight.local` | `AdminAlpha2026!` | Manage users, view full audit log trail, access all patient cases and ICU stays across departments. |
| **Senior Reviewer** | `reviewer@omnimed-insight.local` | `Reviewer!2026` | Inspect completed cases, review XAI evidence, approve or reject report drafts. (Write/Edit disabled). |
| **Clinical Observer** | `readonly@omnimed-insight.local` | `Readonly!2026` | Read-only view of patient charts and completed reports. (All mutations blocked). |
| **Isolated Clinician** | `dr.other@omnimed-insight.local` | `Clinician!2026` | Assigned exclusively to `pat-synth-003`. Used for testing cross-patient IDOR boundaries. |

---

## 7. Step-by-Step Clinical Workflow Guide

1. **Sign In**: Log in as `clinician@omnimed-insight.local` with password `Clinician!2026`.
2. **Patient & Case Registry**:
   * Navigate to the **Patients & Cases** tab.
   * Click **`+ Tambah Pasien Baru (+ Add Patient)`** to register a new synthetic patient with custom vitals and clinical history.
   * On any patient card, click **`+ Buka Kasus Baru`** to launch a new CXR or Brain MRI imaging case.
3. **Image & XAI Workspace**:
   * Select a case. Upload a PA chest radiograph or brain MRI scan (PNG/JPEG).
   * Click **`Execute Medical Image & Grad-CAM Analysis`**. PyTorch DenseNet-121 runs forward and backward passes, computing class logits and spatial sensitivity maps.
   * Adjust the **Grad-CAM Opacity Slider** (0%–100%), switch **Invert LUT**, and zoom in to inspect attribution focus.
   * Enter optional attending notes and click **`Generate Evidence-Grounded Report Draft →`**.
4. **ICU Early Warning (6–12h)**:
   * Switch to the **ICU Early Warning (6–12h)** tab to monitor active ICU stays (`MICU`, `SICU`, `CCU`, `MSICU`).
   * Inspect longitudinal vital trajectories (`HR`, `MAP`, `SBP/DBP`, `Resp`, `SpO2`, `Temp`, `Lactate`), run live **LightGBM + Tree SHAP** risk inference, review local SHAP directional attributions, and sign off active sepsis alerts.
5. **Report Drafting & Sign-Off**:
   * The workspace switches to the **Report Drafting & Review** tab.
   * Inspect the synthesized 5-part report (sourced facts, model predictions, Grad-CAM quadrant summary, impression narrative, and mandatory safety limitations).
   * Switch between draft versions using the **Daftar Versi Laporan** bar (`v1`, `v2`, etc.).
   * In the right column, enter clinical attestation notes and click **`Approve Draft`** or **`Reject Draft`**.
6. **FHIR R4 Bundle Export**:
   * Open the **FHIR R4 Bundle** tab to inspect or download the complete interoperable HL7 FHIR JSON bundle.
7. **Audit & System Status**:
   * Switch to the **Audit & System Status** tab to review the immutable audit log recording your actions with timestamp and user ID.

---

## 8. Automated Testing & Verification

Every layer contains dedicated automated test suites:

### 1. Python AI Service Tests (PyTest)
```bash
python -m pytest ai-service-python/tests -v
# Output: 19 passed (10 Imaging XAI/Checkpoint/Calibration/Rollback tests + 9 ICU Cohort/Monotonic-SHAP/Calibration/Anti-Leakage tests)
```

### 2. Rust Backend Security & Integration Tests (Cargo Test)
```bash
cd backend-rust
cargo test
# Output: 6 passed
# - test_health_and_authentication_lifecycle ... ok
# - test_cross_patient_idor_prevention_and_rbac_boundaries ... ok
# - test_report_drafting_clinician_review_and_fhir_r4_bundle ... ok
# - test_icu_stays_listing_and_rbac_boundaries ... ok
# - test_icu_workspace_idor_and_alert_lifecycle ... ok
# - test_research_telemetry_serde_defaults_and_idempotent_column_upgrade ... ok
```

### 3. Frontend Contract, Type & Production Build Validation
```bash
npm --prefix frontend run typecheck
node --test frontend/__tests__/ui_contracts.test.mjs
npm --prefix frontend run build
# Output: 0 TypeScript errors, 4/4 contract tests passed, Next.js production build succeeded
```

---

## 9. Data Governance & Security Disclosures

* **Synthetic Data Labeling**: All seeded and generated records are explicitly tagged with `is_synthetic = 1` and `[SYNTHETIC]` prefixes to eliminate risk of conflation with real protected health information (PHI).
* **Network Isolation**: By default, no medical data or imaging tensors leave the local host. External cloud LLMs (such as Med-PaLM or cloud Llama endpoints) are disabled by default until explicit institutional governance and BAA/DPA agreements are established.
* **Audit Trail**: Every authentication attempt, patient view, image upload, model inference, report sign-off, and FHIR export is permanently written to the `audit_logs` table.

---

## 📄 License
This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details. Developed for medical imaging research, decision-support methodology demonstration, and explainable AI engineering.
