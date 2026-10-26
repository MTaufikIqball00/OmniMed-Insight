use std::env;
use std::path::PathBuf;

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub bind_host: String,
    pub frontend_port: u16,
    pub rust_backend_port: u16,
    pub python_ai_port: u16,
    pub fhir_server_port: u16,
    pub postgres_port: u16,
    pub frontend_origin: String,
    pub python_ai_service_url: String,
    pub fhir_server_url: String,
    pub database_url: String,
    pub session_secret: String,
    pub internal_service_token: String,
    pub session_ttl_hours: i64,
    pub cookie_secure: bool,
    pub bootstrap_admin_email: String,
    pub bootstrap_admin_password: String,
    pub seed_synthetic_demo: bool,
    pub max_upload_size_bytes: usize,
    pub storage_dir: PathBuf,
}

impl AppConfig {
    pub fn from_env() -> Self {
        let _ = dotenvy::dotenv();

        let bind_host = env::var("BIND_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
        let frontend_port = env::var("FRONTEND_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(3100);
        let rust_backend_port = env::var("RUST_BACKEND_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(8100);
        let python_ai_port = env::var("PYTHON_AI_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(8200);
        let fhir_server_port = env::var("FHIR_SERVER_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(8300);
        let postgres_port = env::var("POSTGRES_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(5433);

        let frontend_origin = env::var("FRONTEND_ORIGIN")
            .unwrap_or_else(|_| format!("http://{}:{}", bind_host, frontend_port));
        let python_ai_service_url = env::var("PYTHON_AI_SERVICE_URL")
            .unwrap_or_else(|_| format!("http://{}:{}", bind_host, python_ai_port));
        let fhir_server_url = env::var("FHIR_SERVER_URL")
            .unwrap_or_else(|_| format!("http://{}:{}/fhir", bind_host, fhir_server_port));

        let database_url = env::var("DATABASE_URL")
            .unwrap_or_else(|_| "sqlite://./data/omnimed.db?mode=rwc".to_string());

        let session_secret = env::var("SESSION_SECRET").unwrap_or_else(|_| {
            "dev-only-ephemeral-session-secret-override-in-env-file-9f8e7d6c5b4a".to_string()
        });
        let internal_service_token = env::var("INTERNAL_SERVICE_TOKEN").unwrap_or_else(|_| {
            "dev-internal-token-override-in-env-file-32-bytes-minimum".to_string()
        });

        let session_ttl_hours = env::var("SESSION_TTL_HOURS")
            .ok()
            .and_then(|v| v.parse::<i64>().ok())
            .unwrap_or(8);

        let cookie_secure = env::var("COOKIE_SECURE")
            .map(|v| v.eq_ignore_ascii_case("true") || v == "1")
            .unwrap_or(false);

        let bootstrap_admin_email = env::var("OMNIMED_BOOTSTRAP_ADMIN_EMAIL")
            .unwrap_or_else(|_| "admin@omnimed-insight.local".to_string());
        let bootstrap_admin_password = env::var("OMNIMED_BOOTSTRAP_ADMIN_PASSWORD")
            .unwrap_or_else(|_| "OmniMed!Admin#2026".to_string());

        let seed_synthetic_demo = env::var("OMNIMED_SEED_SYNTHETIC_DEMO")
            .map(|v| v.eq_ignore_ascii_case("true") || v == "1")
            .unwrap_or(true);

        let max_upload_size_bytes = env::var("MAX_UPLOAD_SIZE_BYTES")
            .ok()
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(15 * 1024 * 1024);

        let storage_dir = PathBuf::from(
            env::var("STORAGE_DIR").unwrap_or_else(|_| "./data/storage".to_string()),
        );

        Self {
            bind_host,
            frontend_port,
            rust_backend_port,
            python_ai_port,
            fhir_server_port,
            postgres_port,
            frontend_origin,
            python_ai_service_url,
            fhir_server_url,
            database_url,
            session_secret,
            internal_service_token,
            session_ttl_hours,
            cookie_secure,
            bootstrap_admin_email,
            bootstrap_admin_password,
            seed_synthetic_demo,
            max_upload_size_bytes,
            storage_dir,
        }
    }
}
