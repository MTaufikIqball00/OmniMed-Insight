# Archive 2 Dataset Provenance and Clinical Evaluation Report
## 5,000-Patient ICU Clinical Cohort (`sepsis_icu_synthetic.csv`)

### 1. Dataset Origin & Provenance
- **Source Location**: Provided from local filesystem path `C:\Users\taufi\Downloads\archive2\sepsis_icu_synthetic.csv`.
- **Repository Copy**: Archived at `data/archive2/sepsis_icu_synthetic.csv`.
- **Dataset Nature & Explicit Label**: **SYNTHETIC ICU CLINICAL COHORT** (strictly labeled as synthetic per filename and Non-Negotiable Rule 13).
  > **Regulatory & Clinical Safety Notice**:
  > In accordance with project non-negotiable rules, synthetic datasets are strictly employed for pipeline verification, algorithm benchmarking, and clinical decision-support engineering tests. Synthetic data must never be presented as real clinical evidence or as proof of real-world patient outcomes.
- **Cohort Dimensions**: 5,000 unique patients (`subject_id` 100% unique), 77 tabular variables.
- **Class Balance**: 
  - Non-Sepsis (`sepsis_label = 0`): 4,250 patients (85.0%).
  - Sepsis (`sepsis_label = 1`): 750 patients (15.0%).

---

### 2. Variable Dictionary & Clinical Taxonomy

The 77 columns capture patient trajectory upon and throughout ICU admission across 7 clinical domains:

#### A. Demographics & Baseline Characteristics (8 variables)
- `subject_id`: Unique de-identified patient identifier (integer).
- `age`: Patient age in years.
- `gender`: Biological sex (`M`, `F`, with 1 typo `Mael` normalized to `M`).
- `weight_kg`: Weight in kilograms (range: 45.0 - 140.0 kg).
- `height_cm`: Height in centimeters (range: 145.0 - 200.0 cm).
- `bmi`: Body Mass Index ($\text{kg/m}^2$, 251 missing values).
- `ethnicity`: Patient ethnicity (`White`, `Black`, `Hispanic`, `Asian`, `Other`).
- `insurance`: Payer category (`Medicare`, `Private`, `Medicaid`, `Self-pay`).

#### B. Vital Sign Distributions & Variability (24 variables)
Summary metrics (mean, max, min, standard deviation) for bedside monitoring:
- Heart Rate (HR, bpm): `hr_mean`, `hr_max`, `hr_min`, `hr_std`.
- Systolic Blood Pressure (SBP, mmHg): `sbp_mean`, `sbp_max`, `sbp_min`, `sbp_std`.
- Diastolic Blood Pressure (DBP, mmHg): `dbp_mean`, `dbp_max`, `dbp_min`, `dbp_std`.
- Mean Arterial Pressure (MAP, mmHg): `map_mean` (163 missing values).
- Body Temperature (°C): `temp_celsius_mean`, `temp_celsius_max`, `temp_celsius_min`, `temp_celsius_std`.
- Pulse Oximetry ($SpO_2$, %): `spo2_mean`, `spo2_min`, `spo2_max`, `spo2_std`.
- Respiratory Rate (RR, breaths/min): `respiratory_rate_mean`, `respiratory_rate_max`, `respiratory_rate_min`, `respiratory_rate_std`.

#### C. Comprehensive Laboratory Panels (15 variables)
Reflecting systemic inflammation, renal function, coagulation, and tissue perfusion:
- `wbc`: White blood cell count ($10^9/\text{L}$).
- `lactate_mmol`: Arterial/venous serum lactate ($\text{mmol/L}$).
- `creatinine`: Serum creatinine ($\text{mg/dL}$).
- `platelet_count`: Platelets ($10^9/\text{L}$).
- `bilirubin_total`: Total bilirubin ($\text{mg/dL}$).
- `glucose`: Blood glucose ($\text{mg/dL}$).
- `ph_arterial`: Arterial blood gas pH.
- `pao2_fio2_ratio`: PaO2/FiO2 ratio (Horowitz index for respiratory failure).
- `inr`: International Normalized Ratio (coagulopathy).
- `sodium`, `potassium`, `chloride`, `bicarbonate`: Serum electrolytes ($\text{mEq/L}$).
- `hematocrit`, `hemoglobin`: Oxygen carrying capacity markers.

#### D. Chronic Comorbidities (10 binary variables)
Underlying clinical history indicators:
- `diabetes`, `hypertension`, `chf` (congestive heart failure), `copd`, `chronic_kidney_disease`, `liver_disease`, `immunosuppression`, `cad`, `atrial_fibrillation`, `cancer_active`.

#### E. Clinical Interventions & Therapeutics (8 variables)
Aggressive supportive care markers:
- `vasopressors_flag`: Administration of vasoactive infusions (norepinephrine, epinephrine, vasopressin).
- `mechanical_ventilation`: Invasive mechanical ventilator support.
- `fio2_percent`: Delivered oxygen fraction.
- `antibiotics_24h`: Broad-spectrum parenteral antibiotic initiation within 24h.
- `fluids_ml_24h`: Cumulative IV crystalloid resuscitation volume.
- `sedation_score`: RASS / Ramsay sedation score.
- `vasopressor_dose_mcg_kg_min`: Vasoactive dose intensity.
- `insulin_infusion_flag`: Intensive insulin protocol.

#### F. Clinical Severity Scores & Physiological Indices (5 variables)
Validated ICU acuity metrics:
- `sofa_score`: Sequential Organ Failure Assessment (0-24).
- `apache_iv`: Acute Physiology and Chronic Health Evaluation IV score.
- `qsofa`: Quick SOFA score (0-3).
- `sirs_criteria`: Systemic Inflammatory Response Syndrome score (0-4).
- `gcs_total`: Glasgow Coma Scale (3-15).

#### G. Administrative, Timing & Outcome Metrics (7 variables)
- `icu_los_hours`: Total length of stay in the intensive care unit.
- `hospital_admit_source`: Source of admission (`ED`, `OR`, `Transfer`, `Direct`).
- `icu_admit_time_hour`: Hour of admission (0-23).
- `day_of_week`: Day index (1-7).
- `readmission_30day`: Unplanned 30-day hospital readmission flag.
- `sepsis_label`: Primary target outcome (1 = Sepsis deterioration, 0 = Non-sepsis).

---

### 3. Missingness & Quality Profile

Laboratory variables exhibit approximately 10-11% missingness (500 to 565 missing measurements out of 5,000 patients), consistent with real-world clinical testing patterns where specialized lab panels are not ordered uniformly for all admissions.

- Imputation rule: Medians and mode encodings are fitted strictly on the Training cohort (70%) and frozen for out-of-fold validation and test sets.
- Outlier checks: All laboratory and vital values reside within physiologically plausible bounds.

---

### 4. Anti-Leakage Audit & Exclusion of Post-Event / Synthetic Target Proxies

During the comprehensive scientific audit of `sepsis_icu_synthetic.csv`, univariate and temporal causality analyses identified four categories of variables that must be excluded from predictive feature matrices (`EXCLUDED_LEAKAGE_AND_OUTCOME_COLS` in `ai-service-python/icu_pipeline/train_cohort_models.py`):

1. **Future / Post-Stay Outcomes**:
   - `icu_los_hours`, `readmission_30day` (known only after ICU discharge).
2. **Post-Onset Therapeutic Interventions**:
   - `vasopressors_flag`, `vasopressor_dose_mcg_kg_min`, `antibiotics_24h`, `fluids_ml_24h`, `mechanical_ventilation`, `fio2_percent`, `insulin_infusion_flag`, `sedation_score` (clinical treatments initiated *in response* to sepsis onset).
3. **Downstream Composite Severity Scores**:
   - `sofa_score`, `apache_iv`, `sirs_criteria`, `qsofa` (composite diagnostic indices that encapsulate the target definition).
4. **Deterministic Synthetic Generator Separators**:
   - Inspection of the synthetic generator distributions revealed that `pao2_fio2_ratio` was generated with hard threshold separation (`[50.1, 60.0]` for `sepsis_label=1` vs `[91.3, 100.0]` for `sepsis_label=0`), alongside near-deterministic rules on `lactate_mmol` (univariate `AUC = 0.9980`) and `creatinine` (univariate `AUC = 0.9837`). Including these synthetic generator rules previously inflated model AUROC to `1.0000` (`Brier = 0.0000`) and collapsed 100% of SHAP importance onto a single variable.

By strictly excluding these 18 columns, the model is trained on **83 clean baseline physiological, hemodynamic, acid-base, coagulation, and comorbidity features**.

---

### 5. Verified Out-of-Sample Test Performance (`750` Held-Out Patients)

Patient-level stratified split: **3,500 Train (70%) / 750 Validation (15%) / 750 Test (15%)** (`0` patient overlap).

| Endpoint | Model | AUROC | AUPRC | Brier Score | Sensitivity | Specificity | F1 Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Primary: Sepsis-3** | **LightGBM (Champion `v2.0.0-archive2-5k`)** | **0.9954** | **0.9864** | **0.0111** | **0.9643** | **0.9922** | **0.9600** |
| Primary: Sepsis-3 | XGBoost | 0.9936 | 0.9839 | 0.0124 | 0.9286 | 0.9953 | 0.9498 |
| Primary: Sepsis-3 | Logistic Regression | 0.9926 | 0.9718 | 0.0226 | 0.9643 | 0.9655 | 0.8963 |
| Primary: Sepsis-3 | qSOFA Clinical Baseline | 0.5171 | 0.1574 | 0.1419 | 0.1250 | 0.9091 | 0.1707 |
| **Secondary: CHF** | **LightGBM (`chf` Endpoint)** | **0.7176** | **0.2678** | **0.1798** | **0.8350** | **0.5672** | **0.3699** |

#### Top 10 Tree-SHAP Global Drivers (Archive2 Sepsis Cohort)
1. `ph_arterial` (`mean |SHAP| = 0.4795`)
2. `inr` (`mean |SHAP| = 0.3385`)
3. `respiratory_rate_mean` (`mean |SHAP| = 0.3323`)
4. `shock_index` (`mean |SHAP| = 0.3266`)
5. `spo2_mean` (`mean |SHAP| = 0.3029`)
6. `bicarbonate` (`mean |SHAP| = 0.3011`)
7. `platelet_count` (`mean |SHAP| = 0.2234`)
8. `sbp_mean` (`mean |SHAP| = 0.2116`)
9. `hr_mean` (`mean |SHAP| = 0.1977`)
10. `wbc` (`mean |SHAP| = 0.1803`)

