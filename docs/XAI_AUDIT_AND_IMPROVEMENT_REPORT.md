# OmniMed Insight — Laporan Audit Menyeluruh & Perbaikan Explainable AI (XAI)

> **Status Dokumen:** Audit Teknis, Kalibrasi Numerik, Perbaikan Visual & UX Klinis  
> **Cakupan Modul:**  
> 1. **Medical Image XAI (PyTorch DenseNet-121 Grad-CAM / HiResCAM)** — `ai-service-python/app/xai_engine.py`, `frontend/src/components/MedicalImageViewer.tsx`, `frontend/src/app/page.tsx`, `frontend/src/lib/cloudFallback.ts`  
> 2. **ICU Early Warning XAI (LightGBM + Tree SHAP)** — `ai-service-python/app/icu_engine.py`, `backend-rust/src/db.rs`, `frontend/src/components/IcuEarlyWarningWorkspace.tsx`, `frontend/src/lib/cloudFallback.ts`

---

## 1. Ringkasan Temuan Audit: Mengapa XAI Sebelumnya Hanya Menampilkan Merah & Memusingkan?

Hasil audit terhadap kode backend (Python/Rust), artefak overlay PNG tersimpan (`data/storage/overlays/*_gradcam.png`), tangkapan layar aplikasi (`docs/image/OmniMed.png`), serta antarmuka Next.js menemukan **7 masalah kritis**:

### A. Temuan pada Image XAI (Grad-CAM)
1. **Ledakan Numerik Logit hingga 568–789 Juta (`BatchNorm Variance Explosion`)**
   - **Penyebab:** Pada `ai-service-python/app/xai_engine.py` versi sebelumnya, DenseNet-121 diinisialisasi menggunakan `nn.init.kaiming_normal_(..., mode="fan_out")` tanpa mengkalibrasi buffer `running_mean` dan `running_var` milik `BatchNorm2d`. Pada arsitektur DenseNet yang memiliki 58 *bottleneck layer* (rasio `fan_in / fan_out` hingga 8:1), varians sinyal meledak secara eksponensial ketika berjalan di mode `.eval()`.
   - **Bukti Terukur:**
     - `synth_cxr_case_001.png` menghasilkan logit kelas ke-3 (`CXR_CARDIOMEGALY_BORDERLINE`) sebesar **`568,591,168.0`**.
     - `synth_mri_case_002.png` menghasilkan logit sebesar **`594,177,216.0`**.
     - Foto X-Ray asli (`img-981911ed-e87a-44c3-aa0f-59c22457be13.jpg` yang memiliki kavitas nyata di paru kanan atas) menghasilkan logit sebesar **`789,515,456.0`**.
   - **Akibatnya:** Model selalu mengunci prediksi pada 1 kelas dengan skor **100.0%**, fitur gambar asli tenggelam 500 juta banding 1, dan peta aktivasi selalu terpusat pada bayangan jantung/tulang belakang di tengah gambar.
2. **Overlay Menutupi 97.1% Gambar dengan Gumpalan Merah di Tengah ("Merah Doang")**
   - **Penyebab:** Selain logit yang meledak, fungsi `jet_colormap_rgba` melompat ke opasitas **`0.37`** pada nilai rendah `0.12` hingga **`0.95` (`alpha=242/255`)** tanpa ambang transparan yang memadai.
   - **Bukti Terukur:** Semua 6 file overlay di `data/storage/overlays/` memiliki **`97.0%–97.7%` piksel non-transparan** (`alpha > 30`) dan **`41.3%–42.1%` area kuning/oranye/merah** yang menutupi jaringan paru sehat maupun lesi.
3. **Kesalahan Orientasi Anatomis Kiri vs Kanan & Heatmap Statis pada Cloud Demo (`cloudFallback.ts`)**
   - Pada radiografi PA dada standar, **sisi kiri layar adalah Paru Kanan pasien (Right Lung)**. Namun di `cloudFallback.ts`, phantom & lingkaran merah digambar di sisi kanan (`cx=328`, `x=0.64`) sementara metadatanya melabeli **Right Lower Zone (RLZ)**. Selain itu, gambar apa pun yang di-upload pada mode Vercel/Cloud Demo sebelumnya mengabaikan isi piksel asli gambar dan selalu menempelkan lingkaran merah radius 115px di koordinat yang sama.
4. **Bug Tampilan `Shannon Entropy: -0.00 bits` & Jargon Teknis**
   - IEEE floating-point `-0.0` saat probabilitas 100% muncul langsung di UI dan laporan (`OmniMed.png` / `OmniMed2.png`) sebagai `-0` / `-0.00 bits`, disertai istilah mentah (*"features.denseblock4"*, *"mean 0.69 | peak 1.00"*) tanpa penjelasan awam.

### B. Temuan pada ICU Early Warning XAI (Tree SHAP)
5. **Seluruh Bar SHAP Pasien Default Berwarna Merah Penuh (`stay-synth-001` & `stay-synth-004`)**
   - Data awal pada `db.rs` dan `cloudFallback.ts` hanya mencantumkan fitur `INCREASES_RISK` tanpa faktor penahan normal (`DECREASES_RISK`), dan rumus lebar bar (`Math.min(100, Math.abs(sVal) * 150)%`) membuat semua fitur dengan SHAP `>= 0.67` mentok ke lebar 100% merah penuh.
6. **Kontradiksi Penjelasan Laktat Tinggi vs Arah SHAP Negatif (`icu_engine.py`)**
   - Pada model LightGBM yang dilatih dari 118 pasien PhysioNet 2019 (di mana >90% baris tidak memiliki pengukuran Laktat dan diimputasi median `1.8–2.0`), pohon keputusan membelah `Lactate <= 1.46` ke arah positif sehingga `Lactate_roll_max_6h = 3.7` menghasilkan `shap = -0.4111 (DECREASES_RISK)`. Namun `icu_engine.py` sebelumnya mencetak teks statis *"hallmark septic shock"*, sehingga warna hijau `DECREASES_RISK` bertabrakan langsung dengan narasinya.
7. **Tidak Adanya Pembanding Nilai Normal & Ringkasan Langkah Lanjutan**
   - Angka mentah SHAP seperti `+0.972` dan nilai vital tanpa rentang normal (misalnya `Pulse Pressure 36` tanpa keterangan `Normal: 40–60 mmHg`) menyulitkan pengguna awam maupun klinisi untuk langsung memahami kesimpulan model.

---

## 2. Perbaikan yang Telah Diimplementasikan

1. **Kalibrasi DenseNet-121 + HiResCAM Terfokus (`ai-service-python/app/xai_engine.py`)**:
   - Mengganti inisialisasi ke `mode="fan_in"`, mengkalibrasi `BatchNorm2d` (`running_mean`/`running_var`), dan menurunkan skala bobot classifier sehingga logit berada di rentang stabil (tidak lagi meledak ke ratusan juta).
   - Menggunakan **HiResCAM** pada vektor fitur `denseblock4` L2-normalized yang dipadukan secara *differentiable* dengan deteksi anomali parenkim anatomis (mengecualikan tepi watermark dan menekan bias tulang belakang/jantung normal).
   - Memperbarui `jet_colormap_rgba` agar nilai rendah (`< 0.24`) **100% transparan (`alpha = 0`)**, kontur diperhalus dengan filter Gaussian, dan puncak merah dibatasi maksimal opasitas `0.72` agar jaringan anatomi asli tetap terlihat jelas.
   - Menghilangkan angka `-0.0` dengan sanitasi `max(0.0, round(entropy, 4)) + 0.0`.
2. **Saliency Berbasis Piksel Nyata & Koreksi Kiri/Kanan pada Cloud Demo (`frontend/src/lib/cloudFallback.ts`)**:
   - Mengoreksi lesi & koordinat `Right Lower Zone (RLZ)` ke sisi kiri layar (`cx=175, cy=344`, `peak=[0.34, 0.67]`).
   - Menambahkan fungsi `analyzeUploadedImageOnCanvas` yang membaca matriks piksel gambar upload pengguna langsung di HTML5 `<canvas>` browser untuk menghasilkan overlay XAI yang sesuai dengan gambar yang diunggah.
   - Menambahkan faktor stabilisasi hijau (`MAP_latest`) pada `stay-synth-001` agar keseimbangan faktor risiko vs penahan terlihat jelas.
3. **Kontekstualisasi SHAP Tanpa Kontradiksi (`ai-service-python/app/icu_engine.py`, `backend-rust/src/db.rs`)**:
   - Mengganti kamus teks statis dengan fungsi `_build_contextual_rationale(...)` yang menyesuaikan penjelasan terhadap nilai pasien aktual dan menjelaskan jujur jika bobot statistik cohort berbeda dari kewaspadaan klinis bedside.
4. **Perombakan UX agar Mudah Dipahami (`MedicalImageViewer.tsx`, `page.tsx`, `IcuEarlyWarningWorkspace.tsx`)**:
   - **Mode `"Bandingkan"` (Side-by-Side Original vs Grad-CAM)** dan penanda **Fokus Puncak AI (crosshair)** serta default transparansi lebih nyaman (**48%**).
   - **Panduan Cepat "Cara Mudah Membaca Warna XAI"** (Bening vs Kuning vs Merah).
   - Kartu **"Ringkasan Mudah Dipahami & Rekomendasi Lanjutan"** baik pada Workspace Citra Medis maupun pada Workspace ICU SHAP (lengkap dengan pembanding **Nilai Normal** dan bar SHAP proporsional terhadap nilai maksimum pasien).

---

## 3. Implementasi Upgrade Riset (Wave 1–3) & Hasil Pengukuran Empiris (*Before vs. After*)

Menindaklanjuti rekomendasi audit di atas, platform ditingkatkan secara menyeluruh dengan prinsip **integritas ilmiah absolut** (seluruh fitting kalibrator & pemilihan ambang keputusan dilakukan **eksklusif pada *validation split***, evaluasi akhir **sekali pada *held-out test split***, tanpa fabrikasi data klinis atau *DUA bypass*).

### A. Peningkatan Medical Imaging Pipeline, Checkpoint Integrity & Post-Hoc Calibration

- **Audit Kesenjangan Dataset (`docs/IMAGING_MODEL_PROVENANCE.md`):**
  - Diverifikasi secara langsung bahwa `data/storage/uploads/` hanya memuat 4 sampel unggahan (duplikat gambar demo yang sama) dan 2 phantom sintetis, serta paket `torchxrayvision`, `timm`, dan `monai` tidak terpasang secara lokal (`False`).
  - Dataset radiologi eksternal besar (NIH ChestX-ray14 ~45 GB, Stanford CheXpert [memerlukan DUA], PhysioNet MIMIC-CXR [memerlukan CITI + DUA], RSNA Pneumonia, BraTS Brain MRI [memerlukan DUA Synapse]) **tidak tersedia secara lokal** dan tidak pernah di-scrape/bypass.
- **Pipeline Training & Kalibrasi Reproducible (`ai-service-python/imaging_pipeline/`):**
  - `dataset.py` & `train_densenet.py` mendukung dua mode: `--manifest-csv` (untuk kohort radiologi berizin resmi) dan `--synthetic-benchmark` (`SYNTHETIC_BENCHMARK_FIXTURE`: 240 pasien sintetis unik / 480 citra CXR 4-kelas, *patient-level stratified split* 70/15/15 = **168 train [336 citra] / 36 val [72 citra] / 36 test [72 citra]** dengan verifikasi `zero_patient_leakage_verified = True`).
  - `calibrate_densenet.py` membandingkan `TemperatureScaler` vs `MulticlassPlattScaler` secara eksklusif pada `val_logits.npz` (`n = 72`, `acc = 1.0000`, `NONE` NLL = `0.0004` vs `TEMPERATURE_SCALING` NLL = `0.0000`, `T = 0.4780`), memilih `TEMPERATURE_SCALING`, lalu mengevaluasi pada *held-out* `test_logits.npz` (`n = 72`).
  - `MedicalDenseNetXaiEngine` (`app/xai_engine.py`) memvalidasi `MODEL_WEIGHTS_PATH` + `MODEL_WEIGHTS_EXPECTED_SHA256`, bentuk arsitektur (`densenet121`, 4 kelas), finiteness bobot, dan *dummy forward pass* (`|logit| < 100.0`), dengan *fail-safe rollback* ke `RESEARCH_UNVERIFIED` jika ada anomali.

| Metrik / Status Imaging (`CXR 4-Class`) | Before (Default Backbone Init) | After (`CUSTOM_CHECKPOINT` Uncalibrated) | After (`CALIBRATED_CHECKPOINT`: `TEMPERATURE_SCALING`) |
| :--- | :---: | :---: | :---: |
| **Status Runtime & Provenance** | `RESEARCH_UNVERIFIED` (`UNINITIALIZED_RESEARCH_BACKBONE`) | `CUSTOM_CHECKPOINT` (`SYNTHETIC_BENCHMARK_FIXTURE`) | `CALIBRATED_CHECKPOINT` (`SYNTHETIC_BENCHMARK_FIXTURE`) |
| **Artefak & SHA-256** | Tidak ada file `.pt` | `densenet121_cxr_synthetic_benchmark.pt` (`0373da881e13...`) | `densenet121_cxr_calibrated.pt` (`f4024854cc67...`) |
| **Held-out Test Accuracy (`n = 72`)** | N/A (bobot acak Kaiming) | `0.9722` (97.22%) | `0.9722` (97.22%) |
| **Held-out Test ECE (10 bins)** | N/A (Belum terkalibrasi) | `0.0190` | `0.0216` (Platt scaling pembanding: `0.0212`) |
| **Held-out Test Brier / NLL** | N/A | `0.0085` / `0.0600` (`max\|logit\| = 16.9507`) | `0.0113` / `0.0981` (`T = 0.4780`) |
| **Reliability Bins (Test)** | `[]` (kosong) | `[0.4,0.5)` n=1, `[0.7,0.8)` n=1, `[0.9,1.0]` n=70 | `[0.6,0.7)` `avg=0.6205, emp=0.0, n=1`; `[0.9,1.0]` `avg=0.9991, emp=0.9859, n=71` |

> [!WARNING]
> **Keterbatasan OOD (`SYNTHETIC_BENCHMARK_FIXTURE` vs. Gambar Ber-watermark):** Uji asap pada phantom `app.synthetic_fixtures.generate_synthetic_cxr` (yang memiliki *text banner* putih di tepi atas/bawah) menyebabkan checkpoint benchmark memfokuskan aktivasi HiResCAM pada *banner* teks bawah-kiri (`peak=[0.1758, 0.8555]`) dan memprediksi `CXR_PARENCHYMAL_OPACITY` baik untuk `focal=True` (`0.9971`) maupun `focal=False` (`0.9898`). Ini membuktikan bahwa benchmark sintetis **hanya memverifikasi mekanisme pipeline, stabilitas numerik, dan kalibrasi in-distribution**, dan **bukan** model radiologi klinis hingga dilatih ulang via `--manifest-csv` pada kohort klinis terkurasi bebas *overlay* teks.

---

### B. Ekspansi Kohort PhysioNet 2019, Monotonic Clinical Guard & Kalibrasi ICU (`LightGBM + SHAP`)

- **Ekspansi Kohort Nyata PhysioNet Challenge 2019 (`CC BY 4.0`, `docs/ICU_DATASET_PROVENANCE.md`):**
  - Diperluas dari **118 stay eligible (4,615 baris)** menjadi **988 stay eligible (38,270 baris per jam)** dari 1,000 file `.psv` nyata (`492` Hospital System A + `496` Hospital System B; **0 file sintetis dicampur**), mencakup **59 stay positif sepsis** dan **407 baris warning 6–12 jam**.
  - Partisi *patient-level stratified* 70/15/15 (`PASSED_ZERO_OVERLAP`): Train **691 stay** (`41` pos, `27,179` baris), Validation **148 stay** (`9` pos, `5,466` baris), Test **149 stay** (`9` pos, `5,625` baris, `63` baris pos).
- **Monotonic Constraints & Stratified TreeSHAP Background (`train_models.py`):**
  - Diterapkan `monotone_constraints_method="advanced"` pada 22 variabel fisiologis kritis: `+1` untuk 15 fitur (`Lactate_*`, `shock_index`, `map_hypoperfusion_depth`, `qsofa_vital_score`, `HR_*`, `Resp_*`, `temp_deviation`, `Creatinine_latest`, `BUN_latest`) dan `-1` untuk 7 fitur (`MAP_*`, `SBP_latest`, `O2Sat_latest`, `Platelets_latest`, `HCO3_roll_min_6h`).
  - Latar belakang `shap.TreeExplainer` diganti dari `iloc[:100]` menjadi sampel stratifikasi 200 baris (`train_test_split(..., stratify=y_train)`), dengan pemisahan ketat antara `champion_model.joblib` (booster mentah untuk SHAP eksak) dan `calibrator.joblib` (`FrozenEstimator` di-fit hanya pada `val.csv`).
- **Verifikasi Anti-Inversi Polaritas SHAP (Counterfactual Regression Tests):**
  - Kenaikan `Lactate` (`1.1 -> 4.5 mmol/L`) meningkatkan SHAP `Lactate_latest` secara monoton (`-0.0134 -> +0.1488`) tanpa pernah muncul sebagai `DECREASES_RISK` pada `4.5 mmol/L`.
  - Penurunan `MAP` (`85 -> 55 mmHg`) meningkatkan SHAP `MAP_roll_min_6h` (`-0.0040 -> +0.0058`) dan `MAP_roll_mean_6h` (`-0.0126 -> +0.0215`) tanpa pernah berbalik arah menjadi `DECREASES_RISK`.

#### Tabel Perbandingan Eksperimental ICU (Held-Out Test Set)

| Model / Tahap Eksperimen | Kohort Test | AUROC | AUPRC | Brier | ECE (10 bins) | Sensitivitas | Spesifisitas | F1 | Threshold | Monotonic Guard |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Lama (118 stays, Uncalibrated)** | 18 stays (`782` rows) | `0.8663` | `0.0660` | `0.0232` | `0.0512` | `1.0000` | `0.5644` | `0.0720` | `0.0326` | `OFF` (SHAP Laktat terbalik) |
| **qSOFA Clinical Baseline (988 stays)** | 149 stays (`5,625` rows) | `0.5469` | `0.0125` | `0.1098` | `0.1765` | `0.4127` | `0.6845` | `0.0282` | `0.5000` | N/A |
| **Logistic Regression (988 stays)** | 149 stays (`5,625` rows) | `0.7237` | `0.0297` | `0.1622` | `0.2961` | `0.5397` | `0.7492` | `0.0456` | `0.4700` | `OFF` |
| **XGBoost (988 stays)** | 149 stays (`5,625` rows) | `0.7376` | `0.0309` | `0.0235` | `0.1116` | `0.5079` | `0.7524` | `0.0435` | `0.1233` | `OFF` |
| **LightGBM Unconstrained (988 stays)** | 149 stays (`5,625` rows) | `0.7699` | `0.0458` | `0.0109` | `0.0037` | `0.7143` | `0.6507` | `0.0439` | `0.0057` | `OFF` |
| **LightGBM Monotonic (Uncalibrated)** | 149 stays (`5,625` rows) | `0.7822` | `0.0688` | `0.0108` | `0.0039` | `0.6667` | `0.7310` | `0.0525` | `0.0073` | **`ACTIVE`** |
| **Champion: LightGBM Monotonic + `ISOTONIC_CALIBRATION`** | 149 stays (`5,625` rows) | **`0.7817`** | `0.0486` | **`0.0108`** | **`0.0005`** | `0.6508` | **`0.7504`** | **`0.0550`** | **`0.0200`** | **`ACTIVE`** |

- **Evaluasi Kohort Archive2 (`5,000` Pasien Sintetis, `83` Fitur, Anti-Leakage Filtered, *Held-Out Test* `n = 750`):**
  - *Before* (`NONE_UNCALIBRATED`): AUROC = `0.9954`, AUPRC = `0.9864`, Brier = `0.0111`, NLL = `0.0528`, **ECE = `0.0225`**, Sens = `0.9196`, Spec = `0.9953`, F1 = `0.9450`.
  - *After* (`PLATT_SCALING`, dipilih via validasi OOF Brier `0.0039` / NLL `0.0194` / ECE `0.0045`): AUROC = `0.9954`, AUPRC = `0.9864`, Brier = `0.0116`, NLL = `0.0513`, **ECE = `0.0104`** (penurunan ECE **53.8%**), Sens = `0.9196`, Spec = `0.9953`, Prec = `0.9717`, F1 = `0.9450`, `calibrated_threshold = 0.67`, `monotone_constraints_active = False`.
  - Catatan jujur: Archive2 merupakan data sintetis tabular (`data/archive2/sepsis_icu_synthetic.csv`), dan endpoint sekunder CHF tetap tidak terkalibrasi secara klinis (`AUROC = 0.7176`, `ECE = 0.2271`).

---

## 4. Kesenjangan Tersisa & Roadmap Lanjutan

1. **Pelatihan Ulang Imaging pada Kohort Klinis Resmi (`--manifest-csv`):**
   - Pipeline `--manifest-csv` telah siap untuk data NIH ChestX-ray14, CheXpert, MIMIC-CXR, RSNA Pneumonia, atau irisan MRI BraTS setelah akses DUA institusional diperoleh. Bobot `SYNTHETIC_BENCHMARK_FIXTURE` tidak boleh diklaim memiliki performa diagnostik pasien nyata.
2. **Validasi Multi-Senter Prospektif & Skala Besar ICU (MIMIC-IV / eICU):**
   - Meskipun ekspansi PhysioNet 2019 ke 988 stay dan kalibrasi Isotonik menurunkan ECE menjadi `0.0005` serta menaikkan spesifisitas menjadi `75.04%` (dibanding `56.44%` sebelumnya), prevalensi sepsis yang rendah (`1.12%` baris uji) membatasi *positive predictive value* (`precision = 0.0287`). Diperlukan validasi pada kohort longitudinal skala ≥ 5,000–40,000 stay sebelum studi prospektif.
3. **Studi Kegunaan Klinis (*Clinician Human-in-the-Loop Evaluation*):**
   - Lakukan evaluasi kualitatif menggunakan mode **"Bandingkan"**, badge status kalibrasi/provenance, kurva reliabilitas mini, serta indikator **Monotonic Clinical Guard: ACTIVE** pada radiolog dan dokter ICU untuk mengukur dampaknya terhadap beban kognitif dan pencegahan *automation bias*.
