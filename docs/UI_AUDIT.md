# OmniMed Insight (XAI) — Tailwind CSS UI/UX & Accessibility Audit Report

## 1. Environment & Styling System Inspection

| Aspect | Verified Implementation | Affected Files |
| :--- | :--- | :--- |
| **Framework** | Next.js `14.2.15` (App Router, React `18.3.1`, TypeScript `5.6.3`) | `frontend/package.json`, `frontend/tsconfig.json` |
| **Primary Styling System** | **Tailwind CSS v3 (`^3.4.14`)** with PostCSS & Autoprefixer | `frontend/tailwind.config.ts`, `frontend/postcss.config.mjs`, `frontend/src/app/globals.css` |
| **Port & API Binding** | Frontend bound to `http://127.0.0.1:3100`; canonical API target `http://127.0.0.1:8100` | `frontend/next.config.mjs`, `frontend/src/lib/api.ts` |

---

## 2. UI/UX Audit Findings & Implemented Safeguards

During the design and audit of the clinical interface, the following healthcare UX, accessibility, and clinical safety requirements were verified and implemented:

1. **Zero Decorative Buttons or Fake Metrics**:
   - **Audit Check**: Verified that `frontend/src/app/page.tsx` and `frontend/src/components/MedicalImageViewer.tsx` contain zero placeholder buttons or hardcoded metric counters.
   - **Implementation**: Every metric card on the Overview Dashboard (`authorized_patients_count`, `authorized_cases_count`, `completed_xai_analyses`, `pending_report_drafts`, `approved_reports`) is populated strictly from `/api/dashboard` SQLx queries.
2. **Distinguishing Implemented vs. Unverified vs. Unavailable Features**:
   - **Audit Check**: Model outputs and capabilities must never imply autonomous diagnostic clearance.
   - **Implementation**: Added a persistent top clinical safety bar (`DECISION SUPPORT ONLY • SYNTHETIC DATA`), explicit `RESEARCH_UNVERIFIED` badges on all DenseNet-121 outputs, Shannon entropy / uncertainty banners (`LOW`, `MODERATE`, `HIGH_UNCERTAINTY`), and a live Capability Matrix on the Overview tab showing `IMPLEMENTED`, `RESEARCH_UNVERIFIED`, and `UNAVAILABLE / DISABLED` (for external cloud LLMs).
3. **Medical Image Viewer & Grad-CAM Attribution Controls**:
   - **Audit Check**: Clinicians must be able to inspect the unaltered original image without destructive cropping or permanently baked-in heatmaps.
   - **Implementation**: `MedicalImageViewer.tsx` renders the read-only original scan (with SHA-256 integrity HUD, `75%–300%` zoom, directional pan, and LUT inversion) and composites the separate RGBA Grad-CAM overlay dynamically with a `0%–100%` opacity slider, quick toggle (`XAI Heatmap ON` / `Unaltered Original Only`), thermal color-bar legend (`0.00` to `1.00`), and mandatory attribution warning.
4. **Evidence-Grounded Report Drafting & Provenance Separation**:
   - **Audit Check**: Reports must separate sourced clinical facts, model predictions, XAI attribution, and clinician impression narrative.
   - **Implementation**: The Report Drafting workspace (`activeTab === "reports"`) renders 5 distinct labeled sections alongside an interactive `Evidence Provenance Chain` panel displaying `[FACT-CASE-...]`, `[OBS-...]`, `[AI-...]`, and `[XAI-...]` citations, plus mandatory reviewer attestation notes before `APPROVE` or `REJECT`.
5. **Keyboard Accessibility & Focus Visibility**:
   - **Audit Check**: All interactive controls require visible keyboard focus indicators and semantic labels.
   - **Implementation**: Configured global `focus-visible:ring-2 focus-visible:ring-sky-600` in `frontend/src/app/globals.css`, semantic `<nav aria-label="Primary Workspace Navigation">`, `role="alert"` banners, and explicit `htmlFor`/`id` and `aria-label` attributes on form inputs and selects.
