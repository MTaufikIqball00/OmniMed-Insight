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

## 3. Rekomendasi Lanjutan (Roadmap Riset & Pengembangan)

1. **Integrasi Bobot Model Radiologi Terlatih (`MODEL_WEIGHTS_PATH`)**:
   - Saat ini status model citra masih **`RESEARCH_UNVERIFIED`** (tanpa bobot terlatih pada dataset radiologi besar). Untuk penggunaan riset diagnostik yang sesungguhnya, latih atau muat checkpoint DenseNet-121 tervalidasi (mis. dari **NIH ChestX-ray14**, **CheXpert**, atau **MIMIC-CXR** untuk CXR; **BraTS** untuk Brain MRI) ke environment `MODEL_WEIGHTS_PATH`.
2. **Kalibrasi Probabilitas (*Platt Scaling / Isotonic Calibration*)**:
   - Terapkan kalibrasi probabilitas pasca-pelatihan pada *validation split* terpisah agar persentase confidence benar-benar selaras dengan *empirical post-test probability* (ECE < 0.05) sebelum dipakai pada studi klinis.
3. **Peningkatan Dataset Longitudinal ICU & Monotonic Constraints pada LightGBM**:
   - Pada model ICU (`train_models.py`), latih ulang pada kohort PhysioNet / MIMIC-IV / eICU skala penuh (`>= 5,000` pasien sepsis longitudinal) dengan *monotonic constraints* klinis (`monotone_constraints` di LightGBM untuk variabel kunci seperti Laktat ↑ -> risiko tidak boleh ↓) guna mencegah artefak pohon akibat *imputation bias*.
4. **Studi Kegunaan Klinis (*Clinician Human-in-the-Loop Evaluation*)**:
   - Lakukan evaluasi kualitatif menggunakan mode **"Bandingkan"** pada radiolog/dokter jaga untuk mengukur apakah tampilan side-by-side + crosshair menurunkan waktu inspeksi tanpa menyebabkan *automation bias*.
