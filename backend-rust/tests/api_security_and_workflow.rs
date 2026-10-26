use axum::{
    body::Body,
    http::{header, Request, StatusCode},
};
use http_body_util::BodyExt;
use omnimed_backend_rust::{
    build_app_router, config::AppConfig, db::init_db, routes::AppState,
};
use serde_json::{json, Value};
use std::sync::Arc;
use tempfile::TempDir;
use tower::ServiceExt;

async fn setup_test_app() -> (axum::Router, TempDir) {
    let temp_dir = TempDir::new().expect("Failed to create temp dir");
    let mut cfg = AppConfig::from_env();
    cfg.database_url = "sqlite::memory:".to_string();
    cfg.storage_dir = temp_dir.path().join("storage");
    cfg.bootstrap_admin_email = "admin@omnimed-insight.local".to_string();
    cfg.bootstrap_admin_password = "AdminTestPassword!2026".to_string();
    cfg.seed_synthetic_demo = true;

    let pool = init_db(&cfg).await.expect("Failed to init test DB");
    let client = reqwest::Client::new();
    let state = Arc::new(AppState {
        db: pool,
        config: cfg,
        http_client: client,
    });

    (build_app_router(state), temp_dir)
}

async fn login_as(app: &axum::Router, email: &str, password: &str) -> (String, String) {
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::to_vec(&json!({
                "email": email,
                "password": password
            }))
            .unwrap(),
        ))
        .unwrap();

    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&bytes).unwrap();
    let token = body["session_token"].as_str().unwrap().to_string();
    let csrf = body["csrf_token"].as_str().unwrap().to_string();
    (token, csrf)
}

#[tokio::test]
async fn test_health_and_authentication_lifecycle() {
    let (app, _tmp) = setup_test_app().await;

    // 1. Health endpoint
    let req = Request::builder()
        .uri("/health")
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);

    // 2. Reject invalid credentials
    let bad_login = Request::builder()
        .method("POST")
        .uri("/api/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::to_vec(&json!({
                "email": "clinician@omnimed-insight.local",
                "password": "WrongPassword123"
            }))
            .unwrap(),
        ))
        .unwrap();
    let bad_resp = app.clone().oneshot(bad_login).await.unwrap();
    assert_eq!(bad_resp.status(), StatusCode::UNAUTHORIZED);

    // 3. Valid login & session check
    let (token, _csrf) = login_as(&app, "clinician@omnimed-insight.local", "Clinician!2026").await;

    let me_req = Request::builder()
        .uri("/api/auth/me")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();
    let me_resp = app.clone().oneshot(me_req).await.unwrap();
    assert_eq!(me_resp.status(), StatusCode::OK);

    // 4. Logout revokes session immediately
    let logout_req = Request::builder()
        .method("POST")
        .uri("/api/auth/logout")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();
    let logout_resp = app.clone().oneshot(logout_req).await.unwrap();
    assert_eq!(logout_resp.status(), StatusCode::OK);

    let after_logout_req = Request::builder()
        .uri("/api/auth/me")
        .header(header::AUTHORIZATION, format!("Bearer {}", token))
        .body(Body::empty())
        .unwrap();
    let after_resp = app.clone().oneshot(after_logout_req).await.unwrap();
    assert_eq!(after_resp.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_cross_patient_idor_prevention_and_rbac_boundaries() {
    let (app, _tmp) = setup_test_app().await;

    let (clin_token, _) = login_as(&app, "clinician@omnimed-insight.local", "Clinician!2026").await;
    let (ro_token, _) = login_as(&app, "readonly@omnimed-insight.local", "Readonly!2026").await;
    let (admin_token, _) =
        login_as(&app, "admin@omnimed-insight.local", "AdminTestPassword!2026").await;

    // 1. Clinician can access assigned patient `pat-synth-001`
    let ok_pat_req = Request::builder()
        .uri("/api/patients/pat-synth-001")
        .header(header::AUTHORIZATION, format!("Bearer {}", clin_token))
        .body(Body::empty())
        .unwrap();
    let ok_pat_resp = app.clone().oneshot(ok_pat_req).await.unwrap();
    assert_eq!(ok_pat_resp.status(), StatusCode::OK);

    // 2. Clinician is BLOCKED (403 Forbidden) from unassigned patient `pat-synth-003` (IDOR check)
    let idor_req = Request::builder()
        .uri("/api/patients/pat-synth-003")
        .header(header::AUTHORIZATION, format!("Bearer {}", clin_token))
        .body(Body::empty())
        .unwrap();
    let idor_resp = app.clone().oneshot(idor_req).await.unwrap();
    assert_eq!(idor_resp.status(), StatusCode::FORBIDDEN);

    // 3. Clinician cannot access Admin user management endpoint
    let admin_ep_req = Request::builder()
        .uri("/api/admin/users")
        .header(header::AUTHORIZATION, format!("Bearer {}", clin_token))
        .body(Body::empty())
        .unwrap();
    let admin_ep_resp = app.clone().oneshot(admin_ep_req).await.unwrap();
    assert_eq!(admin_ep_resp.status(), StatusCode::FORBIDDEN);

    // 4. Read-only user cannot create a clinical case
    let ro_create_req = Request::builder()
        .method("POST")
        .uri("/api/cases")
        .header(header::AUTHORIZATION, format!("Bearer {}", ro_token))
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::to_vec(&json!({
                "patient_id": "pat-synth-001",
                "encounter_type": "Consult",
                "modality": "CXR",
                "body_part": "CHEST",
                "chief_complaint": "Test",
                "clinical_history": "Test",
                "priority": "ROUTINE"
            }))
            .unwrap(),
        ))
        .unwrap();
    let ro_create_resp = app.clone().oneshot(ro_create_req).await.unwrap();
    assert_eq!(ro_create_resp.status(), StatusCode::FORBIDDEN);

    // 5. Verify Audit Log recorded the RBAC_DENIED event
    let audit_req = Request::builder()
        .uri("/api/admin/audit-logs")
        .header(header::AUTHORIZATION, format!("Bearer {}", admin_token))
        .body(Body::empty())
        .unwrap();
    let audit_resp = app.clone().oneshot(audit_req).await.unwrap();
    assert_eq!(audit_resp.status(), StatusCode::OK);
    let audit_bytes = audit_resp.into_body().collect().await.unwrap().to_bytes();
    let audit_json: Value = serde_json::from_slice(&audit_bytes).unwrap();
    let logs = audit_json["audit_logs"].as_array().unwrap();
    assert!(logs
        .iter()
        .any(|l| l["event_action"] == "UNAUTHORIZED_PATIENT_ACCESS_ATTEMPT"));
}

#[tokio::test]
async fn test_report_drafting_clinician_review_and_fhir_r4_bundle() {
    let (app, _tmp) = setup_test_app().await;

    let (clin_token, _) = login_as(&app, "clinician@omnimed-insight.local", "Clinician!2026").await;
    let (rev_token, _) = login_as(&app, "reviewer@omnimed-insight.local", "Reviewer!2026").await;

    // 1. Clinician generates evidence-grounded report draft for case-synth-001
    let draft_req = Request::builder()
        .method("POST")
        .uri("/api/cases/case-synth-001/reports/draft")
        .header(header::AUTHORIZATION, format!("Bearer {}", clin_token))
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::to_vec(&json!({
                "clinician_context_note": "Correlate right basilar crackles with radiographic findings."
            }))
            .unwrap(),
        ))
        .unwrap();
    let draft_resp = app.clone().oneshot(draft_req).await.unwrap();
    assert_eq!(draft_resp.status(), StatusCode::CREATED);
    let draft_bytes = draft_resp.into_body().collect().await.unwrap().to_bytes();
    let draft_json: Value = serde_json::from_slice(&draft_bytes).unwrap();
    let report_id = draft_json["report"]["id"].as_str().unwrap().to_string();
    assert_eq!(draft_json["report"]["status"], "DRAFT_PENDING_REVIEW");

    // 2. Reviewer approves the draft with sign-off attestation
    let review_req = Request::builder()
        .method("POST")
        .uri(format!("/api/reports/{}/review", report_id))
        .header(header::AUTHORIZATION, format!("Bearer {}", rev_token))
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(
            serde_json::to_vec(&json!({
                "decision": "APPROVE",
                "reviewer_notes": "Reviewed sourced observations and phantom imaging. Approved for clinical record."
            }))
            .unwrap(),
        ))
        .unwrap();
    let review_resp = app.clone().oneshot(review_req).await.unwrap();
    assert_eq!(review_resp.status(), StatusCode::OK);
    let rev_bytes = review_resp.into_body().collect().await.unwrap().to_bytes();
    let rev_json: Value = serde_json::from_slice(&rev_bytes).unwrap();
    assert_eq!(rev_json["report"]["status"], "APPROVED");

    // 3. Validate FHIR R4 Bundle generation
    let fhir_req = Request::builder()
        .uri("/api/cases/case-synth-001/fhir-bundle")
        .header(header::AUTHORIZATION, format!("Bearer {}", clin_token))
        .body(Body::empty())
        .unwrap();
    let fhir_resp = app.clone().oneshot(fhir_req).await.unwrap();
    assert_eq!(fhir_resp.status(), StatusCode::OK);
    let fhir_bytes = fhir_resp.into_body().collect().await.unwrap().to_bytes();
    let fhir_json: Value = serde_json::from_slice(&fhir_bytes).unwrap();
    assert_eq!(fhir_json["bundle"]["resourceType"], "Bundle");
    assert_eq!(fhir_json["validation"]["is_valid_r4_structure"], true);
}
