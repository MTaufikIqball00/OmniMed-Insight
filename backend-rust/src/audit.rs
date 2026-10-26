use chrono::Utc;
use sqlx::SqlitePool;
use uuid::Uuid;

pub struct AuditEntry<'a> {
    pub actor_user_id: Option<&'a str>,
    pub actor_email: &'a str,
    pub actor_role: &'a str,
    pub event_category: &'a str,
    pub event_action: &'a str,
    pub resource_type: &'a str,
    pub resource_id: &'a str,
    pub outcome: &'a str,
    pub ip_address: &'a str,
    pub details_redacted: &'a str,
}

pub async fn record_audit_event(pool: &SqlitePool, entry: AuditEntry<'_>) {
    let id = format!("aud-{}", Uuid::new_v4());
    let now = Utc::now().to_rfc3339();
    let res = sqlx::query(
        r#"
        INSERT INTO audit_logs (
            id, actor_user_id, actor_email, actor_role, event_category,
            event_action, resource_type, resource_id, outcome, ip_address,
            details_redacted, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(entry.actor_user_id)
    .bind(entry.actor_email)
    .bind(entry.actor_role)
    .bind(entry.event_category)
    .bind(entry.event_action)
    .bind(entry.resource_type)
    .bind(entry.resource_id)
    .bind(entry.outcome)
    .bind(entry.ip_address)
    .bind(entry.details_redacted)
    .bind(&now)
    .execute(pool)
    .await;

    if let Err(err) = res {
        tracing::error!("Failed to write audit log entry: {}", err);
    }
}
