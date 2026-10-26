use omnimed_backend_rust::{
    build_app_router, config::AppConfig, db::init_db, routes::AppState,
};
use std::{net::SocketAddr, sync::Arc};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "omnimed_backend_rust=info,tower_http=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = AppConfig::from_env();
    let db_pool = init_db(&config)
        .await
        .expect("Failed to initialize OmniMed Insight SQLx database");

    let http_client = reqwest::Client::builder()
        .user_agent("OmniMed-Rust-Security-Boundary/1.0")
        .build()
        .expect("Failed to build internal HTTP client");

    let bind_addr: SocketAddr = format!("{}:{}", config.bind_host, config.rust_backend_port)
        .parse()
        .expect("Invalid BIND_HOST or RUST_BACKEND_PORT");

    let state = Arc::new(AppState {
        db: db_pool,
        config: config.clone(),
        http_client,
    });

    let app = build_app_router(state);

    tracing::info!(
        "OmniMed Insight (XAI) Rust API listening on http://{} (AI Service -> {})",
        bind_addr,
        config.python_ai_service_url
    );

    let listener = tokio::net::TcpListener::bind(bind_addr)
        .await
        .expect("Failed to bind Rust backend TCP listener");

    axum::serve(listener, app)
        .await
        .expect("OmniMed Rust API server terminated unexpectedly");
}
