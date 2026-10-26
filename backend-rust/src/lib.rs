pub mod audit;
pub mod auth;
pub mod config;
pub mod db;
pub mod error;
pub mod models;
pub mod routes;

use axum::{
    extract::DefaultBodyLimit,
    http::{header, HeaderName, HeaderValue, Method},
    routing::{get, patch, post, put},
    Router,
};
use std::sync::Arc;
use tower_http::cors::CorsLayer;

use crate::routes::AppState;

pub fn build_app_router(state: Arc<AppState>) -> Router {
    let origin_str = state.config.frontend_origin.clone();
    let allowed_origin = HeaderValue::from_str(&origin_str)
        .unwrap_or_else(|_| HeaderValue::from_static("http://127.0.0.1:3100"));

    let cors = CorsLayer::new()
        .allow_origin([
            allowed_origin,
            HeaderValue::from_static("http://localhost:3100"),
            HeaderValue::from_static("http://127.0.0.1:3100"),
        ])
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([
            header::CONTENT_TYPE,
            header::AUTHORIZATION,
            header::ACCEPT,
            HeaderName::from_static("x-csrf-token"),
        ])
        .allow_credentials(true);

    let max_body = state.config.max_upload_size_bytes + (512 * 1024);

    Router::new()
        .route("/health", get(routes::health_check))
        .route("/api/system/status", get(routes::system_status))
        .route("/api/auth/login", post(routes::login))
        .route("/api/auth/logout", post(routes::logout))
        .route("/api/auth/me", get(routes::current_session))
        .route("/api/dashboard", get(routes::get_dashboard))
        .route(
            "/api/patients",
            get(routes::list_patients).post(routes::create_patient),
        )
        .route("/api/patients/:patient_id", get(routes::get_patient_detail))
        .route(
            "/api/cases",
            get(routes::list_cases).post(routes::create_case),
        )
        .route("/api/cases/:case_id", get(routes::get_case_workspace))
        .route(
            "/api/cases/:case_id/observations",
            post(routes::add_case_observation),
        )
        .route(
            "/api/cases/:case_id/images",
            post(routes::upload_case_image),
        )
        .route("/api/images/:image_id/raw", get(routes::serve_raw_image))
        .route(
            "/api/cases/:case_id/analyze",
            post(routes::trigger_case_analysis),
        )
        .route("/api/jobs/:job_id", get(routes::get_job_status))
        .route("/api/jobs/:job_id/overlay", get(routes::serve_job_overlay))
        .route(
            "/api/cases/:case_id/reports/draft",
            post(routes::generate_report_draft),
        )
        .route("/api/reports/:report_id", put(routes::update_report_draft))
        .route(
            "/api/reports/:report_id/review",
            post(routes::review_report_draft),
        )
        .route(
            "/api/cases/:case_id/fhir-bundle",
            get(routes::get_or_export_fhir_bundle),
        )
        .route(
            "/api/cases/:case_id/fhir-export",
            post(routes::get_or_export_fhir_bundle),
        )
        .route(
            "/api/admin/users",
            get(routes::admin_list_users).post(routes::admin_create_user),
        )
        .route(
            "/api/admin/users/:user_id",
            patch(routes::admin_update_user),
        )
        .route("/api/admin/audit-logs", get(routes::list_audit_logs))
        .layer(DefaultBodyLimit::max(max_body))
        .layer(cors)
        .with_state(state)
}
