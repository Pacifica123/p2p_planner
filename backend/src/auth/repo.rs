use sqlx::{PgPool, Row};
use uuid::Uuid;

use crate::error::{AppError, AppResult};

use super::dto::DevBootstrapUserResponse;

pub async fn ensure_auth_storage_ready() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth storage is wired but not implemented yet",
    ))
}

pub async fn bootstrap_dev_user(
    pool: &PgPool,
    user_id: Uuid,
    email: &str,
    display_name: &str,
) -> AppResult<DevBootstrapUserResponse> {
    let conflicting_user_id = sqlx::query_scalar::<_, Uuid>(
        r#"
        select id
        from users
        where lower(email) = lower($1)
          and deleted_at is null
          and id <> $2
        limit 1
        "#,
    )
    .bind(email)
    .bind(user_id)
    .fetch_optional(pool)
    .await?;

    if conflicting_user_id.is_some() {
        return Err(AppError::conflict(
            "Another active user already uses this email",
        ));
    }

    let row = sqlx::query(
        r#"
        insert into users (id, email, display_name, password_hash, deleted_at)
        values ($1, $2, $3, null, null)
        on conflict (id) do update
          set email = excluded.email,
              display_name = excluded.display_name,
              deleted_at = null,
              updated_at = now()
        returning id, email, display_name
        "#,
    )
    .bind(user_id)
    .bind(email)
    .bind(display_name)
    .fetch_one(pool)
    .await?;

    Ok(DevBootstrapUserResponse {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        email: row.try_get("email")?,
        display_name: row.try_get("display_name")?,
        mode: "dev_header",
    })
}
