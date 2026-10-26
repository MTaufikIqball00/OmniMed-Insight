use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

#[derive(Debug)]
pub enum AppError {
    Unauthorized(String),
    Forbidden(String),
    NotFound(String),
    BadRequest(String),
    ValidationFailed(String),
    Conflict(String),
    TooManyRequests(String),
    AiServiceUnavailable(String),
    Internal(String),
}

#[derive(Serialize)]
pub struct ErrorBody {
    pub error_code: &'static str,
    pub message: String,
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_code, message) = match self {
            AppError::Unauthorized(msg) => (StatusCode::UNAUTHORIZED, "UNAUTHORIZED", msg),
            AppError::Forbidden(msg) => (StatusCode::FORBIDDEN, "FORBIDDEN_RBAC_OR_SCOPE", msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, "RESOURCE_NOT_FOUND", msg),
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, "BAD_REQUEST", msg),
            AppError::ValidationFailed(msg) => (
                StatusCode::UNPROCESSABLE_ENTITY,
                "VALIDATION_FAILED",
                msg,
            ),
            AppError::Conflict(msg) => (StatusCode::CONFLICT, "RESOURCE_CONFLICT", msg),
            AppError::TooManyRequests(msg) => (
                StatusCode::TOO_MANY_REQUESTS,
                "AUTH_RATE_LIMITED",
                msg,
            ),
            AppError::AiServiceUnavailable(msg) => (
                StatusCode::BAD_GATEWAY,
                "AI_INFERENCE_SERVICE_ERROR",
                msg,
            ),
            AppError::Internal(msg) => {
                tracing::error!("Internal server error: {}", msg);
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "INTERNAL_SERVER_ERROR",
                    "An unexpected server error occurred. Clinical data remains intact.".to_string(),
                )
            }
        };

        (status, Json(ErrorBody { error_code, message })).into_response()
    }
}

impl From<sqlx::Error> for AppError {
    fn from(err: sqlx::Error) -> Self {
        match err {
            sqlx::Error::RowNotFound => AppError::NotFound("Requested record was not found.".into()),
            _ => AppError::Internal(format!("Database error: {}", err)),
        }
    }
}
