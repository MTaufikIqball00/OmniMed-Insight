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
                .map_err(|e| format!("Migration statement failed: {} -- SQL: {}", e, trimmed))?;
        }
    }

    provision_initial_accounts_and_synthetic_data(&pool, config).await?;
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
