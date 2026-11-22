# ICU Early Warning & Sepsis Deterioration Dataset Provenance & Data Dictionary

## 1. Dataset Provenance Record

| Field | Detail |
| :--- | :--- |
| **Dataset Title** | Early Prediction of Sepsis from Clinical Data: Computing in Cardiology Challenge 2019 |
| **Originating Institutions** | MIT Laboratory for Computational Physiology, Emory University, Beth Israel Deaconess Medical Center, Rush University Medical Center |
| **Official PhysioNet Identifier** | `challenge-2019/1.0.0` (DOI: 10.13026/v64v-yn48) |
| **License** | Creative Commons Attribution 4.0 International Public License (CC BY 4.0) |
| **Data Modality** | Hourly longitudinal multivariate ICU time series (vitals, labs, demographics) |
| **Clinical Systems Represented** | Hospital System A (large academic medical center) and Hospital System B (community medical center) |
| **De-identification Standard** | Fully de-identified in compliance with HIPAA Safe Harbor and institutional review board (IRB) protocols |
| **Access Modality** | Open Data via PhysioNet & Registry of Open Data on AWS (`s3://physionet-open/challenge-2019/1.0.0/`) |

---

## 2. Clinical Label & Horizon Definition

### Primary Research Objective: Sepsis-3 Early Warning (6–12h Horizon)
- **Clinical Definition (Sepsis-3)**: Life-threatening organ dysfunction caused by a dysregulated host response to infection. In the dataset, sepsis onset time $t_{sepsis}$ is determined by:
  1. *Suspected Infection*: Blood culture order paired with IV antibiotic administration within a 72h-to-24h clinical window.
  2. *Organ Dysfunction*: Acute increase in total Sequential Organ Failure Assessment (SOFA) score $\ge 2$ points within the infection window.
- **Onset Timestamp ($t_{sepsis}$)**: The earliest chart hour where both infection and organ dysfunction criteria are met.
- **Target Prediction Horizon**: We define a target early-warning window of **6 to 12 hours** prior to $t_{sepsis}$ ($t \in [t_{sepsis}-12, t_{sepsis}-6]$).
- **Censoring & Exclusions**:
  - Patients admitted with pre-existing sepsis ($t_{sepsis} \le 0$ or within the first 4 hours of ICU stay) are excluded from early prediction cohorts because early warning is clinically uninformative when deterioration has already occurred.
  - ICU stays with fewer than 6 hours of observations are excluded to provide sufficient history for rolling baseline calculation.
  - Rows after $t_{sepsis}$ are censored during training to prevent post-event leakage.

---

## 3. Data Dictionary & Physiological Plausibility Ranges

| Variable | Category | Standard Units | LOINC Code | Plausible Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HR** | Vital Sign | beats/min | `8867-4` | [20, 300] | Heart Rate |
| **O2Sat** | Vital Sign | % | `2708-6` | [50, 100] | Peripheral Oxygen Saturation (SpO2) |
| **Temp** | Vital Sign | °C | `8310-5` | [30.0, 45.0] | Core Body Temperature |
| **SBP** | Vital Sign | mmHg | `8480-6` | [40, 280] | Systolic Blood Pressure |
| **MAP** | Vital Sign | mmHg | `8478-0` | [20, 200] | Mean Arterial Pressure |
| **DBP** | Vital Sign | mmHg | `8462-4` | [20, 160] | Diastolic Blood Pressure |
| **Resp** | Vital Sign | breaths/min | `9279-1` | [4, 70] | Respiratory Rate |
| **EtCO2** | Vital Sign | mmHg | `19889-5` | [0, 100] | End-Tidal Carbon Dioxide |
| **BaseExcess** | Lab | mEq/L | `11555-0` | [-30, 30] | Base Excess in blood |
| **HCO3** | Lab | mEq/L | `1963-8` | [5, 60] | Serum Bicarbonate |
| **FiO2** | Lab/Vent | % or fraction | `19996-8` | [0.21, 1.0] | Fraction of Inspired Oxygen |
| **pH** | Lab | pH units | `2744-1` | [6.7, 7.8] | Blood pH |
| **PaCO2** | Lab | mmHg | `2019-8` | [10, 150] | Partial Pressure of Carbon Dioxide |
| **SaO2** | Lab | % | `2713-6` | [50, 100] | Arterial Oxygen Saturation |
| **AST** | Lab | IU/L | `1920-8` | [0, 5000] | Aspartate Aminotransferase |
| **BUN** | Lab | mg/dL | `3094-0` | [1, 200] | Blood Urea Nitrogen |
| **Alkalinephos**| Lab | IU/L | `6768-6` | [0, 2000] | Alkaline Phosphatase |
| **Calcium** | Lab | mg/dL | `17861-6` | [2.0, 20.0] | Serum Calcium |
| **Chloride** | Lab | mEq/L | `2075-0` | [60, 150] | Serum Chloride |
| **Creatinine** | Lab | mg/dL | `2160-0` | [0.1, 25.0] | Serum Creatinine (renal marker) |
| **Bilirubin_total**| Lab | mg/dL | `1975-2` | [0.1, 50.0] | Total Bilirubin (hepatic marker) |
| **Glucose** | Lab | mg/dL | `2345-7` | [20, 1000] | Serum Blood Glucose |
| **Lactate** | Lab | mmol/L | `2524-7` | [0.2, 30.0] | Blood Lactate (tissue hypoperfusion) |
| **Magnesium** | Lab | mg/dL | `2601-3` | [0.5, 10.0] | Serum Magnesium |
| **Phosphate** | Lab | mg/dL | `2777-1` | [0.5, 15.0] | Serum Inorganic Phosphate |
| **Potassium** | Lab | mEq/L | `2823-3` | [1.5, 9.0] | Serum Potassium |
| **Platelets** | Lab | $\times 10^3$/$\mu$L | `777-3` | [5, 1500] | Platelet Count (coagulation marker) |
| **WBC** | Lab | $\times 10^3$/$\mu$L | `6690-2` | [0.1, 100.0] | White Blood Cell Count |
| **Hct** | Lab | % | `4544-3` | [10, 65] | Hematocrit |
| **Hgb** | Lab | g/dL | `718-7` | [3.0, 25.0] | Hemoglobin |
| **PTT** | Lab | seconds | `3173-2` | [15, 150] | Partial Thromboplastin Time |
| **Age** | Demographics | years | `30525-0` | [18, 105] | Patient Age at admission |
| **Gender** | Demographics | binary | `76689-9` | {0: Female, 1: Male} | Biological Sex |
| **Unit1** | Administrative | binary | N/A | {0, 1} | Medical ICU (MICU) indicator |
| **Unit2** | Administrative | binary | N/A | {0, 1} | Surgical ICU (SICU) indicator |
| **HospAdmTime** | Administrative | hours | N/A | [-1000, 50] | Hours before ICU admission |
| **ICULOS** | Time | hours | N/A | [1, 500] | ICU Length of Stay in hours |
| **SepsisLabel** | Outcome | binary | N/A | {0, 1} | Sepsis occurrence indicator |

---

## 4. Cohort Selection & Quality Governance
1. **Source Tracking**: All downloaded files preserve their originating patient IDs (`p000001` - `p020000` from Hospital A; `p100001` - `p120000` from Hospital B).
2. **Missingness Preservation**: Raw records preserve `NaN` representing absent measurements. Imputation is never performed on raw sources; forward-fill with population median fallback is applied strictly on feature-engineered training partitions.
3. **Synthetic Separation**: Any synthetic test datasets generated for offline unit tests are given synthetic prefixes (`pat-icu-synth-...`) and flagged with `is_synthetic = 1`. Synthetic `.psv` trajectories (`pat_synth_*.psv`) are strictly excluded whenever real PhysioNet files are present.

---

## 5. Cohort Expansion, Split Audit & Before-vs-After Provenance

To resolve small-sample validation variance (previously only 2 positive sepsis stays each in validation and test) and imputation-induced SHAP polarity inversion, the cohort was expanded from 120 raw stays to **1,000 real PhysioNet Challenge 2019 ICU stays** (`500` from Hospital System A `p000001`–`p000500` and `500` from Hospital System B `p100001`–`p100500`), strictly excluding synthetic files and verifying zero patient overlap across all 70/15/15 stratified patient-level partitions (`data/icu_processed/data_quality_report.json`).

### Cohort Size Comparison (Before vs. After)

| Metric | Before (Initial Cohort) | After (Expanded Cohort) | Change |
| :--- | :---: | :---: | :---: |
| **Raw PhysioNet `.psv` Files** | 120 | 1,000 (500 Set A + 500 Set B) | +880 stays (8.33x) |
| **Excluded Stays** ($\le 4\text{h}$ onset or $< 4$ eligible rows) | 2 | 12 | +10 |
| **Eligible Unique ICU Stays** | **118** | **988** (492 Hosp A / 496 Hosp B) | **+870 stays (8.37x)** |
| **Total Eligible Hourly Rows** | **4,615** | **38,270** | **+33,655 rows (8.29x)** |
| **Positive Sepsis Stays** | 14 (11.86%) | **59** (5.97%) | **+45 stays (4.21x)** |
| **Negative Stays** | 104 | **929** | +825 stays |
| **Positive 6–12h Warning Rows** | 92 (1.99%) | **407** (1.06%) | **+315 rows (4.42x)** |
| **Patient-Level Overlap Check** | `PASSED_ZERO_OVERLAP` | `PASSED_ZERO_OVERLAP` | Zero leakage verified |

### Stratified 70 / 15 / 15 Patient-Level Partition Breakdown

| Split | Before: Stays (Pos Stays) | Before: Rows (Pos Rows / Ratio) | After: Stays (Pos Stays) | After: Rows (Pos Rows / Ratio) |
| :--- | :---: | :---: | :---: | :---: |
| **Train (70%)** | 82 (10) | 2,987 (65 / 0.0218) | **691 (41)** | **27,179 (281 / 0.0103)** |
| **Validation (15%)** | 18 (2) | 846 (14 / 0.0165) | **148 (9)** | **5,466 (63 / 0.0115)** |
| **Test (15%)** | 18 (2) | 782 (13 / 0.0166) | **149 (9)** | **5,625 (63 / 0.0112)** |
| **Total Eligible** | **118 (14)** | **4,615 (92)** | **988 (59)** | **38,270 (407)** |

### Governance & Leakage Safeguards
1. **Strict Partition Isolation**: Imputation medians (`train_medians`), probability calibration (`Platt Scaling` vs. `Isotonic Calibration`), and decision thresholds (`calibrated_threshold`) are fitted strictly on `train` (medians) or `val` (calibrator and operating threshold). Held-out `test` is evaluated once read-only.
2. **Stratified TreeSHAP Background**: `shap.TreeExplainer` uses a 200-row stratified background subsample from `train.csv` preserving positive sepsis prevalence alongside non-sepsis stays, replacing the previous unstratified `iloc[:100]` slice.
3. **Clinical Monotonicity Constraints**: LightGBM enforces `monotone_constraints_method="advanced"` (`+1` for Lactate/Shock Index/MAP hypoperfusion depth/qSOFA/HR/Resp/temp deviation/Creatinine/BUN; `-1` for MAP/SBP/O2Sat/Platelets/HCO3) to prevent missingness-imputation tree inversions.
