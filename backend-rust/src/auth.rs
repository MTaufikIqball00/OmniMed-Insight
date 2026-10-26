use argon2::{
    password_hash::{rand_core::OsRng, PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use axum::http::{HeaderMap, Method};
use chrono::{DateTime, Utc};
use rand::RngCore;
use sha2::{Digest, Sha256};
use sqlx::{Row, SqlitePool};

use crate::{
    audit::{record_audit_event, AuditEntry},
    error::AppError,
    models::{AuthenticatedUser, UserRole},
};

pub const SESSION_COOKIE_NAME: &str = "omnimed_session";

pub fn hash_password(plain: &str) -> Result<String, AppError> {
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    argon2
        .hash_password(plain.as_bytes(), &salt)
        .map(|h| h.to_string())
        .map_err(|e| AppError::Internal(format!("Password hashing error: {}", e)))
}

pub fn verify_password(plain: &str, hash_str: &str) -> bool {
    let parsed = match PasswordHash::new(hash_str) {
        Ok(p) => p,
        Err(_) => return false,
    };
    Argon2::default()
        .verify_password(plain.as_bytes(), &parsed)
        .is_ok()
}

pub fn generate_random_hex(num_bytes: usize) -> String {
    let mut buf = vec![0u8; num_bytes];
    OsRng.fill_bytes(&mut buf);
    hex::encode(buf)
}

pub fn sha256_hex(input: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input);
    hex::encode(hasher.finalize())
}

pub fn extract_cookie_token(headers: &HeaderMap) -> Option<String> {
    let cookie_header = headers.get(axum::http::header::COOKIE)?.to_str().ok()?;
    for part in cookie_header.split(';') {
        let trimmed = part.trim();
        if let Some(val) = trimmed.strip_prefix(&format!("{}=", SESSION_COOKIE_NAME)) {
            if !val.is_empty() {
                return Some(val.to_string());
            }
        }
    }
    None
}

pub fn extract_bearer_token(headers: &HeaderMap) -> Option<String> {
    let auth_header = headers
        .get(axum::http::header::AUTHORIZATION)?
        .to_str()
        .ok()?;
    auth_header
        .strip_prefix("Bearer ")
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

pub async fn authenticate_request(
    pool: &SqlitePool,
    headers: &HeaderMap,
    method: &Method,
) -> Result<AuthenticatedUser, AppError> {
    let cookie_tok = extract_cookie_token(headers);
    let bearer_tok = extract_bearer_token(headers);

    let (raw_token, used_cookie) = match (cookie_tok, bearer_tok) {
        (Some(c), _) => (c, true),
        (None, Some(b)) => (b, false),
        (None, None) => {
            return Err(AppError::Unauthorized(
                "Authentication required. Please sign in.".into(),
            ))
        }
    };

    let token_hash = sha256_hex(raw_token.as_bytes());
    let row = sqlx::query(
        r#"
        SELECT
            s.id AS session_id,
            s.csrf_token AS csrf_token,
            s.expires_at AS expires_at,
            s.revoked_at AS revoked_at,
            u.id AS user_id,
            u.email AS email,
            u.full_name AS full_name,
            u.role AS role,
            u.specialty AS specialty,
            u.fhir_practitioner_id AS fhir_practitioner_id,
            u.is_active AS is_active
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        "#,
    )
    .bind(&token_hash)
    .fetch_optional(pool)
    .await?;

    let row = row.ok_or_else(|| {
        AppError::Unauthorized("Invalid or expired session token. Please sign in again.".into())
    })?;

    let revoked_at: Option<String> = row.get("revoked_at");
    if revoked_at.is_some() {
        return Err(AppError::Unauthorized(
            "Session has been logged out or revoked.".into(),
        ));
    }

    let is_active: i64 = row.get("is_active");
    if is_active == 0 {
        return Err(AppError::Forbidden(
            "User account is deactivated by administrator.".into(),
        ));
    }

    let expires_at_str: String = row.get("expires_at");
    if let Ok(exp_dt) = DateTime::parse_from_rfc3339(&expires_at_str) {
        if exp_dt.with_timezone(&Utc) < Utc::now() {
            return Err(AppError::Unauthorized(
                "Session has expired. Please sign in again.".into(),
            ));
        }
    }

    let expected_csrf: String = row.get("csrf_token");

    // Enforce CSRF token on state-changing requests when cookie authentication is used
    let is_mutating = matches!(
        *method,
        Method::POST | Method::PUT | Method::PATCH | Method::DELETE
    );
    if used_cookie && is_mutating {
        let supplied_csrf = headers
            .get("X-CSRF-Token")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("");
        if supplied_csrf != expected_csrf {
            return Err(AppError::Forbidden(
                "CSRF validation failed: missing or invalid X-CSRF-Token header.".into(),
            ));
        }
    }

    let role_str: String = row.get("role");

    Ok(AuthenticatedUser {
        user_id: row.get("user_id"),
        email: row.get("email"),
        full_name: row.get("full_name"),
        role: UserRole::from_db(&role_str),
        specialty: row.get("specialty"),
        fhir_practitioner_id: row.get("fhir_practitioner_id"),
        session_id: row.get("session_id"),
        csrf_token: expected_csrf,
    })
}

pub async fn verify_patient_access(
    pool: &SqlitePool,
    user: &AuthenticatedUser,
    patient_id: &str,
) -> Result<(), AppError> {
    // Verify patient exists first
    let exists: Option<(String,)> = sqlx::query_as("SELECT id FROM patients WHERE id = ?")
        .bind(patient_id)
        .fetch_optional(pool)
        .await?;
    if exists.is_none() {
        return Err(AppError::NotFound("Patient record not found.".into()));
    }

    if user.role == UserRole::Admin {
        return Ok(());
    }

    let assigned: Option<(String,)> = sqlx::query_as(
        "SELECT id FROM patient_assignments WHERE patient_id = ? AND user_id = ?",
    )
    .bind(patient_id)
    .bind(&user.user_id)
    .fetch_optional(pool)
    .await?;

    if assigned.is_none() {
        record_audit_event(
            pool,
            AuditEntry {
                actor_user_id: Some(&user.user_id),
                actor_email: &user.email,
                actor_role: user.role.as_str(),
                event_category: "RBAC_DENIED",
                event_action: "UNAUTHORIZED_PATIENT_ACCESS_ATTEMPT",
                resource_type: "patient",
                resource_id: patient_id,
                outcome: "DENIED",
                ip_address: "127.0.0.1",
                details_redacted: "Cross-patient access blocked by server-side assignment boundary.",
            },
        )
        .await;
        return Err(AppError::Forbidden(
            "Access denied: You are not assigned to this patient's care team.".into(),
        ));
    }

    Ok(())
}
