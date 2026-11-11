use chrono::Utc;
use sqlx::{
    sqlite::{SqliteConnectOptions, SqlitePoolOptions},
    SqlitePool,
};
use std::{fs, path::Path, str::FromStr};

use crate::{
    audit::{record_audit_event, AuditEntry},
    auth::{hash_password, sha256_hex},
    config::AppConfig,
};

pub async fn init_db(config: &AppConfig) -> Result<SqlitePool, String> {
    if let Some(stripped) = config.database_url.strip_prefix("sqlite://") {
        let path_part = stripped.split('?').next().unwrap_or(stripped);
        if path_part != ":memory:" {
            if let Some(parent) = Path::new(path_part).parent() {
                let _ = fs::create_dir_all(parent);
            }
        }
    }

    let uploads_dir = config.storage_dir.join("uploads");
    let overlays_dir = config.storage_dir.join("overlays");
    let _ = fs::create_dir_all(&uploads_dir);
    let _ = fs::create_dir_all(&overlays_dir);

    let connect_opts = SqliteConnectOptions::from_str(&config.database_url)
        .map_err(|e| format!("Invalid DATABASE_URL: {}", e))?
        .create_if_missing(true)
        .foreign_keys(true);

    let pool = SqlitePoolOptions::new()
        .max_connections(10)
        .connect_with(connect_opts)
        .await
        .map_err(|e| format!("Failed to connect to SQLx database: {}", e))?;

    let schema_sql = include_str!("../migrations/0001_initial_schema.sql");
    for stmt in schema_sql.split(';') {
        let trimmed = stmt.trim();
        if !trimmed.is_empty() {
            sqlx::query(trimmed)
                .execute(&pool)
                .await
                .map_err(|e| format!("Migration 0001 failed: {} -- SQL: {}", e, trimmed))?;
        }
    }

    let schema_sql_2 = include_str!("../migrations/0002_icu_early_warning_schema.sql");
    for stmt in schema_sql_2.split(';') {
        let trimmed = stmt.trim();
        if !trimmed.is_empty() {
            sqlx::query(trimmed)
                .execute(&pool)
                .await
                .map_err(|e| format!("Migration 0002 failed: {} -- SQL: {}", e, trimmed))?;
        }
    }

    provision_initial_accounts_and_synthetic_data(&pool, config).await?;
    provision_icu_synthetic_demonstration_data(&pool).await?;
    Ok(pool)
}

async fn provision_initial_accounts_and_synthetic_data(
    pool: &SqlitePool,
    config: &AppConfig,
) -> Result<(), String> {
    let existing_users: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
        .fetch_one(pool)
        .await
        .map_err(|e| format!("Failed to count users: {}", e))?;

    if existing_users.0 > 0 {
        return Ok(());
    }

    let now = Utc::now().to_rfc3339();
    let admin_hash = hash_password(&config.bootstrap_admin_password)
        .map_err(|e| format!("Failed to hash bootstrap admin password: {:?}", e))?;

    // 1. Provision Initial Administrator via explicit environment configuration
    sqlx::query(
        r#"
        INSERT INTO users (
            id, email, full_name, role, specialty, fhir_practitioner_id,
            password_hash, is_active, failed_login_attempts, created_at, updated_at
        ) VALUES (?, ?, ?, 'admin', ?, ?, ?, 1, 0, ?, ?)
        "#,
    )
    .bind("usr-admin-001")
    .bind(&config.bootstrap_admin_email)
    .bind("Dr. Elena Vance (System Administrator)")
    .bind("Clinical Informatics & Security")
    .bind("PRAC-SYNTH-ADMIN-001")
    .bind(&admin_hash)
    .bind(&now)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert bootstrap admin: {}", e))?;

    record_audit_event(
        pool,
        AuditEntry {
            actor_user_id: Some("usr-admin-001"),
            actor_email: &config.bootstrap_admin_email,
            actor_role: "admin",
            event_category: "USER_ADMIN",
            event_action: "INITIAL_ADMIN_PROVISIONED",
            resource_type: "user",
            resource_id: "usr-admin-001",
            outcome: "SUCCESS",
            ip_address: "127.0.0.1",
            details_redacted: "Provisioned initial administrator account via bootstrap configuration.",
        },
    )
    .await;

    if !config.seed_synthetic_demo {
        return Ok(());
    }

    // 2. Provision Synthetic Demonstration Accounts for each RBAC role
    let clinician_hash = hash_password("Clinician!2026").map_err(|e| format!("{:?}", e))?;
    let reviewer_hash = hash_password("Reviewer!2026").map_err(|e| format!("{:?}", e))?;
    let readonly_hash = hash_password("Readonly!2026").map_err(|e| format!("{:?}", e))?;

    let demo_users = [
        (
            "usr-clinician-001",
            "clinician@omnimed-insight.local",
            "Dr. Marcus Thorne, MD",
            "clinician",
            "Thoracic & Neuro Diagnostic Radiology",
            "PRAC-SYNTH-CLIN-001",
            &clinician_hash,
        ),
        (
            "usr-reviewer-001",
            "reviewer@omnimed-insight.local",
            "Dr. Priya Nair, MD (Senior Reviewer)",
            "reviewer",
            "Quality Assurance & Neuroradiology",
            "PRAC-SYNTH-REV-001",
            &reviewer_hash,
        ),
        (
            "usr-readonly-001",
            "readonly@omnimed-insight.local",
            "Alex Mercer, RN (Clinical Observer)",
            "readonly",
            "Pulmonary Care Coordination",
            "PRAC-SYNTH-RO-001",
            &readonly_hash,
        ),
        (
            "usr-clinician-002",
            "dr.other@omnimed-insight.local",
            "Dr. Hannah Sterling, MD (Isolated Unit)",
            "clinician",
            "Oncology Imaging",
            "PRAC-SYNTH-CLIN-002",
            &clinician_hash,
        ),
    ];

    for (id, email, name, role, spec, prac_id, pw_hash) in demo_users {
        sqlx::query(
            r#"
            INSERT INTO users (
                id, email, full_name, role, specialty, fhir_practitioner_id,
                password_hash, is_active, failed_login_attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
            "#,
        )
        .bind(id)
        .bind(email)
        .bind(name)
        .bind(role)
        .bind(spec)
        .bind(prac_id)
        .bind(pw_hash)
        .bind(&now)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed demo user {}: {}", email, e))?;
    }

    // 3. Seed Clearly Labeled Synthetic Patients
    let synthetic_patients = [
        (
            "pat-synth-001",
            "SYNTH-MRN-100421",
            "FHIR-PAT-SYNTH-001",
            "[SYNTHETIC] Arthur Pendelton",
            "1958-04-14",
            "male",
            "68yo male synthetic test record presenting with 5-day productive cough, low-grade fever (38.3 C), and decreased right basilar breath sounds.",
            r#"["Penicillin G (Mild rash - Synthetic)"]"#,
            r#"["Community-acquired lower respiratory tract symptoms (Synthetic)", "Essential hypertension (Synthetic)"]"#,
        ),
        (
            "pat-synth-002",
            "SYNTH-MRN-100894",
            "FHIR-PAT-SYNTH-002",
            "[SYNTHETIC] Clara Lindqvist",
            "1974-11-02",
            "female",
            "51yo female synthetic test record evaluated for intermittent visual aura and subacute left parieto-occipital headache.",
            r#"["No Known Drug Allergies (Synthetic)"]"#,
            r#"["Migraine with aura evaluation (Synthetic)", "White matter hyperintensity workup (Synthetic)"]"#,
        ),
        (
            "pat-synth-003",
            "SYNTH-MRN-999003",
            "FHIR-PAT-SYNTH-003",
            "[SYNTHETIC] Restricted Dept Patient (IDOR Boundary Test)",
            "1965-07-22",
            "male",
            "Synthetic patient assigned exclusively to Dr. Hannah Sterling (`usr-clinician-002`) to verify cross-patient RBAC/IDOR blocking.",
            r#"[]"#,
            r#"["Restricted Unit Study (Synthetic)"]"#,
        ),
    ];

    for (id, mrn, fhir_id, name, dob, sex, summary, allergies, conditions) in synthetic_patients {
        sqlx::query(
            r#"
            INSERT INTO patients (
                id, mrn, fhir_patient_id, full_name, birth_date, sex, is_synthetic,
                clinical_summary, allergies_json, active_conditions_json, retention_policy,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'SYNTHETIC_DEV_RETENTION_90D', ?, ?)
            "#,
        )
        .bind(id)
        .bind(mrn)
        .bind(fhir_id)
        .bind(name)
        .bind(dob)
        .bind(sex)
        .bind(summary)
        .bind(allergies)
        .bind(conditions)
        .bind(&now)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed synthetic patient {}: {}", id, e))?;
    }

    // 4. Assign patients 001 and 002 to Clinician 001, Reviewer 001, Readonly 001.
    // Assign patient 003 ONLY to Clinician 002 so IDOR protection is testable.
    let assignments = [
        ("asgn-001", "pat-synth-001", "usr-clinician-001", "PRIMARY_CLINICIAN"),
        ("asgn-002", "pat-synth-001", "usr-reviewer-001", "CONSULTING_REVIEWER"),
        ("asgn-003", "pat-synth-001", "usr-readonly-001", "AUTHORIZED_READONLY"),
        ("asgn-004", "pat-synth-002", "usr-clinician-001", "PRIMARY_CLINICIAN"),
        ("asgn-005", "pat-synth-002", "usr-reviewer-001", "CONSULTING_REVIEWER"),
        ("asgn-006", "pat-synth-002", "usr-readonly-001", "AUTHORIZED_READONLY"),
        ("asgn-007", "pat-synth-003", "usr-clinician-002", "PRIMARY_CLINICIAN"),
    ];

    for (aid, pid, uid, level) in assignments {
        sqlx::query(
            r#"
            INSERT INTO patient_assignments (id, patient_id, user_id, access_level, assigned_by, created_at)
            VALUES (?, ?, ?, ?, 'usr-admin-001', ?)
            "#,
        )
        .bind(aid)
        .bind(pid)
        .bind(uid)
        .bind(level)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed patient assignment {}: {}", aid, e))?;
    }

    // 5. Seed Clinical Cases
    let cases = [
        (
            "case-synth-001",
            "CASE-SYNTH-2026-001",
            "pat-synth-001",
            "usr-clinician-001",
            "Outpatient Acute Respiratory Evaluation",
            "CXR",
            "CHEST",
            "Productive cough, fever 38.3 C, evaluate for right lower lobe infiltrate",
            "Synthetic 68yo male with 5-day history of cough and dyspnea on exertion. Auscultation reveals focal crackles at the right lung base. Ordering PA chest radiograph for decision-support evaluation.",
            "URGENT",
            "OPEN",
            "ENC-SYNTH-2026-001",
        ),
        (
            "case-synth-002",
            "CASE-SYNTH-2026-002",
            "pat-synth-002",
            "usr-clinician-001",
            "Outpatient Neurologic Imaging Consult",
            "MRI",
            "BRAIN",
            "Subacute occipital headache and visual aura, evaluate FLAIR hyperintensities",
            "Synthetic 51yo female with recurrent visual field shimmering and parieto-occipital headache. Neurological motor exam intact. Ordering axial T2-FLAIR Brain MRI scan.",
            "ROUTINE",
            "OPEN",
            "ENC-SYNTH-2026-002",
        ),
    ];

    for (cid, cnum, pid, mcid, etype, mod_str, bpart, cc, hist, prio, stat, enc_id) in cases {
        sqlx::query(
            r#"
            INSERT INTO clinical_cases (
                id, case_number, patient_id, managing_clinician_id, encounter_type,
                modality, body_part, chief_complaint, clinical_history, priority,
                status, fhir_encounter_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(cid)
        .bind(cnum)
        .bind(pid)
        .bind(mcid)
        .bind(etype)
        .bind(mod_str)
        .bind(bpart)
        .bind(cc)
        .bind(hist)
        .bind(prio)
        .bind(stat)
        .bind(enc_id)
        .bind(&now)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed clinical case {}: {}", cid, e))?;
    }

    // 6. Seed Structured Clinical Observations (LOINC coded)
    let observations = [
        (
            "obs-synth-001",
            "case-synth-001",
            "pat-synth-001",
            "8310-5",
            "Body temperature",
            "38.3",
            "degC",
            "36.1 - 37.2",
            "HIGH (Febrile - Synthetic)",
        ),
        (
            "obs-synth-002",
            "case-synth-001",
            "pat-synth-001",
            "59408-5",
            "Oxygen saturation in Arterial blood by Pulse oximetry",
            "94",
            "%",
            "95 - 100",
            "BORDERLINE_LOW (Synthetic)",
        ),
        (
            "obs-synth-003",
            "case-synth-001",
            "pat-synth-001",
            "6690-2",
            "Leukocytes [#/volume] in Blood",
            "12.8",
            "10*3/uL",
            "4.5 - 11.0",
            "ELEVATED (Synthetic)",
        ),
        (
            "obs-synth-004",
            "case-synth-002",
            "pat-synth-002",
            "8480-6",
            "Systolic blood pressure",
            "126",
            "mm[Hg]",
            "90 - 120",
            "NORMAL (Synthetic)",
        ),
        (
            "obs-synth-005",
            "case-synth-002",
            "pat-synth-002",
            "1988-5",
            "C reactive protein [Mass/volume] in Serum or Plasma",
            "2.1",
            "mg/L",
            "0.0 - 5.0",
            "WITHIN_REFERENCE (Synthetic)",
        ),
    ];

    for (oid, cid, pid, loinc, disp, val, unit, rrange, interp) in observations {
        sqlx::query(
            r#"
            INSERT INTO clinical_observations (
                id, case_id, patient_id, loinc_code, display_name, value_text,
                unit, reference_range, interpretation, recorded_by, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'usr-clinician-001', ?)
            "#,
        )
        .bind(oid)
        .bind(cid)
        .bind(pid)
        .bind(loinc)
        .bind(disp)
        .bind(val)
        .bind(unit)
        .bind(rrange)
        .bind(interp)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed observation {}: {}", oid, e))?;
    }

    // 7. Generate and Seed Initial Synthetic Phantom Images (CXR and MRI)
    let uploads_dir = config.storage_dir.join("uploads");
    let cxr_file = uploads_dir.join("synth_cxr_case_001.png");
    let mri_file = uploads_dir.join("synth_mri_case_002.png");

    write_synthetic_grayscale_png(&cxr_file, 256, 256, true)?;
    write_synthetic_grayscale_png(&mri_file, 256, 256, false)?;

    let cxr_bytes = fs::read(&cxr_file).map_err(|e| e.to_string())?;
    let mri_bytes = fs::read(&mri_file).map_err(|e| e.to_string())?;

    let cxr_sha = sha256_hex(&cxr_bytes);
    let mri_sha = sha256_hex(&mri_bytes);

    let seeded_images = [
        (
            "img-synth-001",
            "case-synth-001",
            "pat-synth-001",
            "SYNTHETIC_PHANTOM_CXR_PA_001.png",
            "synth_cxr_case_001.png",
            cxr_file.to_string_lossy().to_string(),
            "CXR",
            "CHEST",
            cxr_bytes.len() as i64,
            cxr_sha,
        ),
        (
            "img-synth-002",
            "case-synth-002",
            "pat-synth-002",
            "SYNTHETIC_PHANTOM_BRAIN_MRI_FLAIR_002.png",
            "synth_mri_case_002.png",
            mri_file.to_string_lossy().to_string(),
            "MRI",
            "BRAIN",
            mri_bytes.len() as i64,
            mri_sha,
        ),
    ];

    for (iid, cid, pid, orig_fn, stor_fn, stor_path, mod_str, bpart, sz, sha) in seeded_images {
        sqlx::query(
            r#"
            INSERT INTO medical_images (
                id, case_id, patient_id, uploaded_by, original_filename, storage_filename,
                storage_path, mime_type, modality, body_part, file_size_bytes,
                sha256_digest, width, height, bit_depth, orientation, metadata_json, created_at
            ) VALUES (?, ?, ?, 'usr-clinician-001', ?, ?, ?, 'image/png', ?, ?, ?, ?, 256, 256, 8, 'NATIVE_UNALTERED (PA/Axial Standard)', '{"synthetic_phantom":true}', ?)
            "#,
        )
        .bind(iid)
        .bind(cid)
        .bind(pid)
        .bind(orig_fn)
        .bind(stor_fn)
        .bind(stor_path)
        .bind(mod_str)
        .bind(bpart)
        .bind(sz)
        .bind(sha)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to seed medical image {}: {}", iid, e))?;
    }

    Ok(())
}

/// Generates a valid, standards-compliant 8-bit grayscale PNG image with an
/// anatomical thoracic/cranial phantom silhouette so synthetic test cases have
/// genuine raster pixel streams immediately upon database initialization.
pub fn write_synthetic_grayscale_png(
    path: &Path,
    width: u32,
    height: u32,
    is_cxr: bool,
) -> Result<(), String> {
    let mut raw_scanlines = Vec::with_capacity(((width + 1) * height) as usize);
    for y in 0..height {
        raw_scanlines.push(0u8); // Filter type 0 (None)
        let ny = (y as f32 - height as f32 / 2.0) / (height as f32 / 2.0);
        for x in 0..width {
            let nx = (x as f32 - width as f32 / 2.0) / (width as f32 / 2.0);
            let val = if is_cxr {
                let mut v = 180.0 - 90.0 * (nx * nx * 0.8 + ny * ny * 0.5);
                let r_lung = ((nx + 0.35) / 0.28).powi(2) + ((ny + 0.04) / 0.56).powi(2);
                let l_lung = ((nx - 0.35) / 0.27).powi(2) + ((ny + 0.04) / 0.55).powi(2);
                let lungs = (-1.8 * r_lung).exp() + (-1.8 * l_lung).exp();
                v -= 110.0 * lungs.clamp(0.0, 1.0);
                // Focal synthetic right lower zone opacity
                let opacity = ((nx + 0.33) / 0.16).powi(2) + ((ny - 0.20) / 0.16).powi(2);
                v += 82.0 * (-2.8 * opacity).exp();
                // Rib modulation
                v += 12.0 * (ny * 26.0).sin() * lungs.clamp(0.0, 1.0);
                v.clamp(12.0, 245.0) as u8
            } else {
                let ell = (nx / 0.72).powi(2) + (ny / 0.84).powi(2);
                let mut v = if ell <= 1.0 { 115.0 - 25.0 * ell } else { 12.0 };
                if ell <= 0.95 {
                    v += 14.0 * (nx * 20.0).sin() * (ny * 20.0).cos();
                }
                let lesion = ((nx - 0.28) / 0.14).powi(2) + ((ny - 0.24) / 0.14).powi(2);
                v += 95.0 * (-3.0 * lesion).exp();
                v.clamp(8.0, 248.0) as u8
            };
            raw_scanlines.push(val);
        }
    }

    let png_bytes = encode_uncompressed_grayscale_png(width, height, &raw_scanlines);
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    fs::write(path, png_bytes).map_err(|e| format!("Failed to write synthetic PNG: {}", e))
}

fn encode_uncompressed_grayscale_png(width: u32, height: u32, scanlines: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    // PNG Magic Header
    out.extend_from_slice(b"\x89PNG\r\n\x1a\n");

    // IHDR chunk (width, height, bit_depth=8, color_type=0 grayscale, comp=0, filter=0, interlace=0)
    let mut ihdr = Vec::with_capacity(13);
    ihdr.extend_from_slice(&width.to_be_bytes());
    ihdr.extend_from_slice(&height.to_be_bytes());
    ihdr.extend_from_slice(&[8, 0, 0, 0, 0]);
    write_png_chunk(&mut out, b"IHDR", &ihdr);

    // Zlib stream wrapping stored (uncompressed) deflate blocks
    let mut zlib = Vec::new();
    zlib.push(0x78); // CMF
    zlib.push(0x01); // FLG

    let mut pos = 0usize;
    let total = scanlines.len();
    while pos < total {
        let chunk_len = (total - pos).min(65535);
        let is_final = pos + chunk_len >= total;
        zlib.push(if is_final { 0x01 } else { 0x00 });
        let len_u16 = chunk_len as u16;
        let nlen_u16 = !len_u16;
        zlib.extend_from_slice(&len_u16.to_le_bytes());
        zlib.extend_from_slice(&nlen_u16.to_le_bytes());
        zlib.extend_from_slice(&scanlines[pos..pos + chunk_len]);
        pos += chunk_len;
    }

    let adler = adler32(scanlines);
    zlib.extend_from_slice(&adler.to_be_bytes());
    write_png_chunk(&mut out, b"IDAT", &zlib);
    write_png_chunk(&mut out, b"IEND", &[]);
    out
}

fn write_png_chunk(out: &mut Vec<u8>, chunk_type: &[u8; 4], data: &[u8]) {
    out.extend_from_slice(&(data.len() as u32).to_be_bytes());
    out.extend_from_slice(chunk_type);
    out.extend_from_slice(data);
    let mut crc_input = Vec::with_capacity(4 + data.len());
    crc_input.extend_from_slice(chunk_type);
    crc_input.extend_from_slice(data);
    let crc = crc32(&crc_input);
    out.extend_from_slice(&crc.to_be_bytes());
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in bytes {
        crc ^= b as u32;
        for _ in 0..8 {
            if crc & 1 != 0 {
                crc = (crc >> 1) ^ 0xedb8_8320;
            } else {
                crc >>= 1;
            }
        }
    }
    !crc
}

fn adler32(bytes: &[u8]) -> u32 {
    let mut a = 1u32;
    let mut b = 0u32;
    for &byte in bytes {
        a = (a + byte as u32) % 65521;
        b = (b + a) % 65521;
    }
    (b << 16) | a
}

async fn provision_icu_synthetic_demonstration_data(pool: &SqlitePool) -> Result<(), String> {
    let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM icu_stays")
        .fetch_one(pool)
        .await
        .map_err(|e| format!("Failed to count icu_stays: {}", e))?;

    if count.0 > 0 {
        return Ok(());
    }

    let now = Utc::now().to_rfc3339();

    // 1. Seed ICU Stays
    let stays = [
        (
            "stay-synth-001",
            "pat-synth-001",
            "MICU",
            "Bed-04",
            "2026-11-10T02:00:00Z",
            14i64,
            "Acute respiratory distress & suspected sepsis secondary to urinary tract infection",
            "DETERIORATING",
        ),
        (
            "stay-synth-002",
            "pat-synth-002",
            "SICU",
            "Bed-07",
            "2026-11-10T08:00:00Z",
            8i64,
            "Post-operative observation following elective endovascular aneurysm repair",
            "STABLE",
        ),
        (
            "stay-synth-003",
            "pat-synth-003",
            "CCU",
            "Bed-02",
            "2026-11-10T06:00:00Z",
            12i64,
            "Non-ST elevation myocardial infarction requiring hemodynamic monitoring",
            "MONITORING",
        ),
        (
            "stay-synth-004",
            "pat-synth-001",
            "MICU",
            "Bed-04",
            "2026-11-09T18:00:00Z",
            27i64,
            "Archive2 Cohort Case #37464: Septic shock with acute renal failure & respiratory distress",
            "CRITICAL",
        ),
    ];

    for (stay_id, pat_id, unit, bed, admit, iculos, syndrome, acuity) in stays {
        sqlx::query(
            r#"
            INSERT INTO icu_stays (
                id, patient_id, icu_unit, bed_number, admit_time,
                iculos_hours, chief_syndrome, acuity_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(stay_id)
        .bind(pat_id)
        .bind(unit)
        .bind(bed)
        .bind(admit)
        .bind(iculos)
        .bind(syndrome)
        .bind(acuity)
        .bind(&now)
        .bind(&now)
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to insert icu_stay {}: {}", stay_id, e))?;
    }

    // 2. Seed Longitudinal Observations for stay-synth-001 (14 hours, showing progressive deterioration)
    let trajectory_001 = [
        // Hour, HR, SBP, DBP, MAP, Resp, Temp, O2Sat, Lactate, WBC
        (1, 78.0, 126.0, 78.0, 94.0, 16.0, 36.8, 98.0, 1.1, 8.2),
        (2, 80.0, 124.0, 76.0, 92.0, 16.0, 36.9, 98.0, 1.1, 8.2),
        (3, 82.0, 122.0, 75.0, 90.6, 17.0, 37.0, 98.0, 1.2, 8.1),
        (4, 85.0, 120.0, 74.0, 89.3, 17.0, 37.2, 97.0, 1.2, 8.0),
        (5, 88.0, 118.0, 72.0, 87.3, 18.0, 37.4, 97.0, 1.4, 7.8),
        (6, 92.0, 115.0, 70.0, 85.0, 19.0, 37.6, 96.0, 1.5, 7.5),
        (7, 96.0, 112.0, 68.0, 82.6, 20.0, 37.7, 96.0, 1.7, 7.0),
        (8, 102.0, 108.0, 66.0, 80.0, 21.0, 37.5, 95.0, 1.9, 6.4),
        (9, 106.0, 104.0, 64.0, 77.3, 22.0, 37.2, 95.0, 2.2, 5.8),
        (10, 110.0, 100.0, 62.0, 74.6, 22.0, 36.8, 94.0, 2.5, 5.1),
        (11, 114.0, 98.0, 60.0, 72.6, 23.0, 36.3, 94.0, 2.8, 4.4),
        (12, 116.0, 95.0, 58.0, 70.3, 24.0, 36.0, 93.0, 3.1, 3.8),
        (13, 118.0, 92.0, 56.0, 68.0, 25.0, 35.8, 93.0, 3.4, 3.4),
        (14, 120.0, 90.0, 54.0, 66.0, 26.0, 35.6, 92.0, 3.7, 3.1),
    ];

    for (h, hr, sbp, dbp, map, resp, temp, o2, lac, wbc) in trajectory_001 {
        let obs_batch = [
            ("HR", hr, "beats/min", "8867-4"),
            ("SBP", sbp, "mmHg", "8480-6"),
            ("DBP", dbp, "mmHg", "8462-4"),
            ("MAP", map, "mmHg", "8478-0"),
            ("Resp", resp, "breaths/min", "9279-1"),
            ("Temp", temp, "°C", "8310-5"),
            ("O2Sat", o2, "%", "2708-6"),
            ("Lactate", lac, "mmol/L", "2524-7"),
            ("WBC", wbc, "x10^3/uL", "6690-2"),
            ("Creatinine", 0.9 + (h as f64 * 0.07), "mg/dL", "2160-0"),
            ("Platelets", 250.0 - (h as f64 * 8.0), "x10^3/uL", "777-3"),
        ];

        let chart_time = format!("2026-11-10T{:02}:00:00Z", 2 + h);

        for (var, val, unit, loinc) in obs_batch {
            let obs_id = format!("obs-001-{:02}-{}", h, var);
            sqlx::query(
                r#"
                INSERT INTO icu_observations (
                    id, stay_id, patient_id, iculos_hour, chart_time,
                    variable_name, valuenum, value_unit, loinc_code, recorded_at
                ) VALUES (?, 'stay-synth-001', 'pat-synth-001', ?, ?, ?, ?, ?, ?, ?)
                "#,
            )
            .bind(&obs_id)
            .bind(h)
            .bind(&chart_time)
            .bind(var)
            .bind(val)
            .bind(unit)
            .bind(loinc)
            .bind(&now)
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to insert icu_obs: {}", e))?;
        }
    }

    // 3. Seed Observations for stay-synth-002 (8 hours, stable post-op)
    for h in 1..=8 {
        let chart_time = format!("2026-11-10T{:02}:00:00Z", 8 + h);
        let obs_batch = [
            ("HR", 72.0 + (h as f64 * 0.5), "beats/min", "8867-4"),
            ("SBP", 122.0 - (h as f64 * 0.4), "mmHg", "8480-6"),
            ("DBP", 74.0, "mmHg", "8462-4"),
            ("MAP", 90.0, "mmHg", "8478-0"),
            ("Resp", 15.0, "breaths/min", "9279-1"),
            ("Temp", 36.9, "°C", "8310-5"),
            ("O2Sat", 99.0, "%", "2708-6"),
            ("Lactate", 1.0, "mmol/L", "2524-7"),
            ("WBC", 7.2, "x10^3/uL", "6690-2"),
        ];

        for (var, val, unit, loinc) in obs_batch {
            let obs_id = format!("obs-002-{:02}-{}", h, var);
            sqlx::query(
                r#"
                INSERT INTO icu_observations (
                    id, stay_id, patient_id, iculos_hour, chart_time,
                    variable_name, valuenum, value_unit, loinc_code, recorded_at
                ) VALUES (?, 'stay-synth-002', 'pat-synth-002', ?, ?, ?, ?, ?, ?, ?)
                "#,
            )
            .bind(&obs_id)
            .bind(h)
            .bind(&chart_time)
            .bind(var)
            .bind(val)
            .bind(unit)
            .bind(loinc)
            .bind(&now)
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to insert icu_obs: {}", e))?;
        }
    }

    // 3b. Seed Observations for stay-synth-003 (8 hours, CCU monitoring)
    for h in 1..=8 {
        let chart_time = format!("2026-11-10T{:02}:00:00Z", 6 + h);
        let obs_batch = [
            ("HR", 84.0 + (h as f64 * 0.8), "beats/min", "8867-4"),
            ("SBP", 116.0 - (h as f64 * 0.6), "mmHg", "8480-6"),
            ("DBP", 70.0 - (h as f64 * 0.3), "mmHg", "8462-4"),
            ("MAP", 85.3 - (h as f64 * 0.4), "mmHg", "8478-0"),
            ("Resp", 18.0 + (h as f64 * 0.2), "breaths/min", "9279-1"),
            ("Temp", 37.2, "°C", "8310-5"),
            ("O2Sat", 96.0, "%", "2708-6"),
            ("Lactate", 1.5, "mmol/L", "2524-7"),
            ("WBC", 9.4, "x10^3/uL", "6690-2"),
            ("Creatinine", 1.2, "mg/dL", "2160-0"),
            ("Platelets", 195.0, "x10^3/uL", "777-3"),
        ];

        for (var, val, unit, loinc) in obs_batch {
            let obs_id = format!("obs-003-{:02}-{}", h, var);
            sqlx::query(
                r#"
                INSERT INTO icu_observations (
                    id, stay_id, patient_id, iculos_hour, chart_time,
                    variable_name, valuenum, value_unit, loinc_code, recorded_at
                ) VALUES (?, 'stay-synth-003', 'pat-synth-003', ?, ?, ?, ?, ?, ?, ?)
                "#,
            )
            .bind(&obs_id)
            .bind(h)
            .bind(&chart_time)
            .bind(var)
            .bind(val)
            .bind(unit)
            .bind(loinc)
            .bind(&now)
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to insert icu_obs stay 003: {}", e))?;
        }
    }

    // 3c. Seed Observations for stay-synth-004 (Archive2 Subject 37464, 6 longitudinal checkpoints)
    for h in 1..=6 {
        let chart_time = format!("2026-11-09T{:02}:00:00Z", 18 + h);
        let obs_batch = [
            ("HR", 75.0 + (h as f64 * 1.6), "beats/min", "8867-4"),
            ("SBP", 124.0 - (h as f64 * 2.0), "mmHg", "8480-6"),
            ("DBP", 72.0 - (h as f64 * 1.2), "mmHg", "8462-4"),
            ("MAP", 89.0 - (h as f64 * 1.4), "mmHg", "8478-0"),
            ("Resp", 20.0 + (h as f64 * 0.6), "breaths/min", "9279-1"),
            ("Temp", 37.0 + (h as f64 * 0.05), "°C", "8310-5"),
            ("O2Sat", 95.0 - (h as f64 * 0.2), "%", "2708-6"),
            ("Lactate", 1.8 + (h as f64 * 0.12), "mmol/L", "2524-7"),
            ("WBC", 6.5 + (h as f64 * 0.04), "x10^3/uL", "6690-2"),
            ("Creatinine", 4.2 + (h as f64 * 0.08), "mg/dL", "2160-0"),
            ("Platelets", 217.0, "x10^3/uL", "777-3"),
        ];

        for (var, val, unit, loinc) in obs_batch {
            let obs_id = format!("obs-004-{:02}-{}", h, var);
            sqlx::query(
                r#"
                INSERT INTO icu_observations (
                    id, stay_id, patient_id, iculos_hour, chart_time,
                    variable_name, valuenum, value_unit, loinc_code, recorded_at
                ) VALUES (?, 'stay-synth-004', 'pat-synth-001', ?, ?, ?, ?, ?, ?, ?)
                "#,
            )
            .bind(&obs_id)
            .bind(h)
            .bind(&chart_time)
            .bind(var)
            .bind(val)
            .bind(unit)
            .bind(loinc)
            .bind(&now)
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to insert icu_obs stay 004: {}", e))?;
        }
    }

    // 4. Seed ICU Model Records (Primary Time-Series & Archive2 Cohort)
    sqlx::query(
        r#"
        INSERT INTO icu_models (
            id, model_id, model_name, version, algorithm, target_endpoint,
            prediction_horizon, decision_threshold, auroc, auprc, brier_score,
            sensitivity, specificity, f1_score, metrics_json, top_features_json, is_active, created_at
        ) VALUES (
            'model-icu-001', 'omnimed-icu-lightgbm-v1', 'LightGBM Temporal Sepsis-3 Early Warning Model',
            '1.0.0', 'lightgbm', 'SEPSIS_DETERIORATION', '6_to_12_hours', 0.0326,
            0.8663, 0.0660, 0.0232, 1.0000, 0.5644, 0.0720,
            '{"auroc":0.8663,"auprc":0.0660,"brier_score":0.0232,"sensitivity":1.0,"specificity":0.5644,"cohort":"PhysioNet Challenge 2019 Test Set"}',
            '[{"feature":"pulse_pressure","importance":0.56194,"rationale":"Narrowing pulse pressure indicates stroke volume collapse"},{"feature":"Lactate_roll_max_6h","importance":0.26021,"rationale":"Peak 6h serum lactate > 2.0 mmol/L reflects tissue hypoperfusion"},{"feature":"Resp_roll_std_6h","importance":0.21338,"rationale":"Respiratory rate volatility reflects compensatory ventilatory drive"}]',
            1, ?
        )
        "#,
    )
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert icu_model-001: {}", e))?;

    sqlx::query(
        r#"
        INSERT INTO icu_models (
            id, model_id, model_name, version, algorithm, target_endpoint,
            prediction_horizon, decision_threshold, auroc, auprc, brier_score,
            sensitivity, specificity, f1_score, metrics_json, top_features_json, is_active, created_at
        ) VALUES (
            'model-icu-002', 'omnimed-icu-cohort-lgbm-v1', 'Archive2 5,000-Patient ICU Cohort Sepsis & CHF Model',
            '1.0.0', 'lightgbm', 'SEPSIS_AND_CHF_DETERIORATION', 'ICU_ADMISSION_AND_STAY', 0.3500,
            0.9954, 0.9864, 0.0111, 0.9643, 0.9922, 0.9600,
            '{"auroc":0.9954,"auprc":0.9864,"brier_score":0.0111,"chf_auroc":0.7176,"chf_auprc":0.2678,"cohort":"Archive2 5,000-Patient Synthetic ICU Cohort (Anti-Leakage Filtered)"}',
            '[{"feature":"ph_arterial","importance":0.47947,"rationale":"Arterial acidemia in uncompensated septic shock"},{"feature":"inr","importance":0.33851,"rationale":"Sepsis-induced coagulopathy marker"},{"feature":"shock_index","importance":0.32664,"rationale":"Heart rate to systolic BP ratio indicating occult shock"}]',
            1, ?
        )
        "#,
    )
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert icu_model-002: {}", e))?;

    // 5. Seed Initial Predictions & Alerts across all seeded stays
    let shap_001 = serde_json::json!([
        {
            "feature": "pulse_pressure",
            "display_name": "Pulse Pressure (SBP - DBP)",
            "current_value": 36.0,
            "shap_value": 0.384,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Narrowing pulse pressure indicates diminishing stroke volume, hypovolemia, or severe systemic vasoconstriction."
        },
        {
            "feature": "Lactate_roll_max_6h",
            "display_name": "6h Peak Serum Lactate (Hypoperfusion)",
            "current_value": 3.7,
            "shap_value": 0.312,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Peak 6-hour serum lactate > 2.0 mmol/L is a hallmark Sepsis-3 criterion for cryptic or overt septic shock."
        },
        {
            "feature": "Temp_roll_min_6h",
            "display_name": "6h Minimum Core Temperature",
            "current_value": 35.6,
            "shap_value": 0.215,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Hypothermia (< 36°C) is a high-risk Sepsis-3 manifestation associated with impaired immune response and shock."
        },
        {
            "feature": "WBC_roll_min_6h",
            "display_name": "6h Minimum White Blood Cell Count",
            "current_value": 3.1,
            "shap_value": 0.142,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Leukopenia (< 4.0 x 10^3/uL) or leukocytosis reflects acute systemic immune activation or consumption."
        },
        {
            "feature": "HR_roll_max_6h",
            "display_name": "6h Peak Heart Rate (Tachycardia)",
            "current_value": 120.0,
            "shap_value": 0.118,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Sustained tachycardia represents compensatory sympathetic surge in response to vasodilation or pyrexia."
        }
    ]).to_string();

    let vital_001 = serde_json::json!({
        "HR": 120.0, "SBP": 90.0, "DBP": 54.0, "MAP": 66.0, "Resp": 26.0,
        "Temp": 35.6, "O2Sat": 92.0, "Lactate": 3.7, "WBC": 3.1, "Creatinine": 1.88, "Platelets": 138.0
    }).to_string();

    sqlx::query(
        r#"
        INSERT INTO icu_predictions (
            id, stay_id, patient_id, requested_by, prediction_time, prediction_horizon,
            risk_score, risk_tier, decision_threshold, model_id, model_version,
            data_quality_status, stale_warning, shap_attributions_json, vital_summary_json, created_at
        ) VALUES (
            'pred-synth-001', 'stay-synth-001', 'pat-synth-001', 'usr-clinician-001',
            'ICU Hour 14', '6_to_12_hours', 0.185, 'CRITICAL', 0.0326,
            'omnimed-icu-lightgbm-v1', '1.0.0', 'ADEQUATE', NULL,
            ?, ?, ?
        )
        "#,
    )
    .bind(&shap_001)
    .bind(&vital_001)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert pred-synth-001: {}", e))?;

    let shap_002 = serde_json::json!([
        {
            "feature": "pulse_pressure",
            "display_name": "Pulse Pressure (SBP - DBP)",
            "current_value": 45.0,
            "shap_value": -0.182,
            "direction": "DECREASES_RISK",
            "clinical_rationale": "Normal pulse pressure reflects preserved stroke volume and arterial compliance."
        },
        {
            "feature": "Lactate_roll_max_6h",
            "display_name": "6h Peak Serum Lactate (Hypoperfusion)",
            "current_value": 1.0,
            "shap_value": -0.145,
            "direction": "DECREASES_RISK",
            "clinical_rationale": "Normal serum lactate (<= 1.5 mmol/L) indicates adequate systemic tissue oxygenation."
        },
        {
            "feature": "HR_roll_max_6h",
            "display_name": "6h Peak Heart Rate (Tachycardia)",
            "current_value": 76.0,
            "shap_value": -0.094,
            "direction": "DECREASES_RISK",
            "clinical_rationale": "Normocardia indicates absence of sympathetic compensatory stress."
        }
    ]).to_string();

    let vital_002 = serde_json::json!({
        "HR": 76.0, "SBP": 119.0, "DBP": 74.0, "MAP": 90.0, "Resp": 15.0,
        "Temp": 36.9, "O2Sat": 99.0, "Lactate": 1.0, "WBC": 7.2
    }).to_string();

    sqlx::query(
        r#"
        INSERT INTO icu_predictions (
            id, stay_id, patient_id, requested_by, prediction_time, prediction_horizon,
            risk_score, risk_tier, decision_threshold, model_id, model_version,
            data_quality_status, stale_warning, shap_attributions_json, vital_summary_json, created_at
        ) VALUES (
            'pred-synth-002', 'stay-synth-002', 'pat-synth-002', 'usr-clinician-001',
            'ICU Hour 8', '6_to_12_hours', 0.0085, 'LOW', 0.0326,
            'omnimed-icu-lightgbm-v1', '1.0.0', 'ADEQUATE', NULL,
            ?, ?, ?
        )
        "#,
    )
    .bind(&shap_002)
    .bind(&vital_002)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert pred-synth-002: {}", e))?;

    let shap_003 = serde_json::json!([
        {
            "feature": "HR_roll_max_6h",
            "display_name": "6h Peak Heart Rate (Tachycardia)",
            "current_value": 90.4,
            "shap_value": 0.042,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Mildly elevated heart rate under CCU observation."
        },
        {
            "feature": "Lactate_latest",
            "display_name": "Latest Serum Lactate",
            "current_value": 1.5,
            "shap_value": -0.038,
            "direction": "DECREASES_RISK",
            "clinical_rationale": "Lactate remains within upper normal reference limits."
        }
    ]).to_string();

    let vital_003 = serde_json::json!({
        "HR": 90.4, "SBP": 111.2, "DBP": 67.6, "MAP": 82.1, "Resp": 19.6,
        "Temp": 37.2, "O2Sat": 96.0, "Lactate": 1.5, "WBC": 9.4, "Creatinine": 1.2, "Platelets": 195.0
    }).to_string();

    sqlx::query(
        r#"
        INSERT INTO icu_predictions (
            id, stay_id, patient_id, requested_by, prediction_time, prediction_horizon,
            risk_score, risk_tier, decision_threshold, model_id, model_version,
            data_quality_status, stale_warning, shap_attributions_json, vital_summary_json, created_at
        ) VALUES (
            'pred-synth-003', 'stay-synth-003', 'pat-synth-003', 'usr-admin-001',
            'ICU Hour 8', '6_to_12_hours', 0.024, 'MODERATE', 0.0326,
            'omnimed-icu-lightgbm-v1', '1.0.0', 'ADEQUATE', NULL,
            ?, ?, ?
        )
        "#,
    )
    .bind(&shap_003)
    .bind(&vital_003)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert pred-synth-003: {}", e))?;

    let shap_004 = serde_json::json!([
        {
            "feature": "Lactate_roll_max_6h",
            "display_name": "6h Peak Serum Lactate (Hypoperfusion)",
            "current_value": 2.52,
            "shap_value": 0.295,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Peak 6-hour serum lactate > 2.0 mmol/L is a hallmark Sepsis-3 criterion for cryptic or overt septic shock."
        },
        {
            "feature": "Resp_roll_max_6h",
            "display_name": "6h Peak Respiratory Rate (Tachypnea)",
            "current_value": 23.6,
            "shap_value": 0.214,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Tachypnea (>= 22 breaths/min) is a core qSOFA indicator of respiratory compensation for acidemia or hypoxia."
        },
        {
            "feature": "Creatinine_latest",
            "display_name": "Latest Serum Creatinine",
            "current_value": 4.68,
            "shap_value": 0.176,
            "direction": "INCREASES_RISK",
            "clinical_rationale": "Severe azotemia (> 4.0 mg/dL) reflects acute kidney injury and septic renal hypoperfusion."
        }
    ]).to_string();

    let vital_004 = serde_json::json!({
        "HR": 84.6, "SBP": 112.0, "DBP": 64.8, "MAP": 80.6, "Resp": 23.6,
        "Temp": 37.3, "O2Sat": 93.8, "Lactate": 2.52, "WBC": 6.74, "Creatinine": 4.68, "Platelets": 217.0
    }).to_string();

    sqlx::query(
        r#"
        INSERT INTO icu_predictions (
            id, stay_id, patient_id, requested_by, prediction_time, prediction_horizon,
            risk_score, risk_tier, decision_threshold, model_id, model_version,
            data_quality_status, stale_warning, shap_attributions_json, vital_summary_json, created_at
        ) VALUES (
            'pred-synth-004', 'stay-synth-004', 'pat-synth-001', 'usr-clinician-001',
            'ICU Hour 6', '6_to_12_hours', 0.148, 'CRITICAL', 0.0326,
            'omnimed-icu-lightgbm-v1', '1.0.0', 'ADEQUATE', NULL,
            ?, ?, ?
        )
        "#,
    )
    .bind(&shap_004)
    .bind(&vital_004)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert pred-synth-004: {}", e))?;

    sqlx::query(
        r#"
        INSERT INTO icu_alerts (
            id, prediction_id, stay_id, patient_id, risk_tier, risk_score,
            alert_time, status, cooldown_until, acknowledged_by, acknowledged_at,
            acknowledgement_notes, created_at
        ) VALUES (
            'alert-synth-001', 'pred-synth-001', 'stay-synth-001', 'pat-synth-001',
            'CRITICAL', 0.185, ?, 'TRIGGERED', NULL, NULL, NULL, NULL, ?
        )
        "#,
    )
    .bind(&now)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert alert-synth-001: {}", e))?;

    sqlx::query(
        r#"
        INSERT INTO icu_alerts (
            id, prediction_id, stay_id, patient_id, risk_tier, risk_score,
            alert_time, status, cooldown_until, acknowledged_by, acknowledged_at,
            acknowledgement_notes, created_at
        ) VALUES (
            'alert-synth-004', 'pred-synth-004', 'stay-synth-004', 'pat-synth-001',
            'CRITICAL', 0.148, ?, 'TRIGGERED', NULL, NULL, NULL, NULL, ?
        )
        "#,
    )
    .bind(&now)
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| format!("Failed to insert alert-synth-004: {}", e))?;

    Ok(())
}

