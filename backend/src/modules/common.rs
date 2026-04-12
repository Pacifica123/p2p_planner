use axum::http::HeaderMap;
use sqlx::{PgPool, Row};
use uuid::Uuid;

use crate::error::{AppError, AppResult};

pub const POSITION_GAP: f64 = 1024.0;

pub fn actor_user_id(headers: &HeaderMap) -> AppResult<Uuid> {
    headers
        .get("x-user-id")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| Uuid::parse_str(value).ok())
        .ok_or_else(|| {
            AppError::unauthorized(
                "Authentication is not wired yet. Pass X-User-Id with an existing user UUID.",
            )
        })
}

pub fn normalize_limit(limit: Option<i64>) -> i64 {
    limit.unwrap_or(50).clamp(1, 100)
}

pub fn trim_to_option(value: Option<String>) -> Option<String> {
    value.and_then(|v| {
        let trimmed = v.trim();
        (!trimmed.is_empty()).then(|| trimmed.to_string())
    })
}

pub async fn ensure_user_exists(pool: &PgPool, user_id: Uuid) -> AppResult<()> {
    let exists = sqlx::query_scalar::<_, bool>(
        r#"
        select exists(
            select 1
            from users
            where id = $1 and deleted_at is null
        )
        "#,
    )
    .bind(user_id)
    .fetch_one(pool)
    .await?;

    if exists {
        Ok(())
    } else {
        Err(AppError::unauthorized("X-User-Id does not match an active user. In local dev, bootstrap it via POST /auth/dev-bootstrap."))
    }
}

pub async fn workspace_role(
    pool: &PgPool,
    workspace_id: Uuid,
    user_id: Uuid,
) -> AppResult<Option<String>> {
    let row = sqlx::query(
        r#"
        select
          case
            when w.owner_user_id = $2 then 'owner'
            else (
              select wm.role
              from workspace_members wm
              where wm.workspace_id = w.id
                and wm.user_id = $2
                and wm.deactivated_at is null
                and wm.deleted_at is null
              limit 1
            )
          end as role,
          w.visibility as visibility
        from workspaces w
        where w.id = $1
          and w.deleted_at is null
        "#,
    )
    .bind(workspace_id)
    .bind(user_id)
    .fetch_optional(pool)
    .await?;

    let Some(row) = row else {
        return Err(AppError::not_found("Workspace not found"));
    };

    let role: Option<String> = row.try_get("role")?;
    let visibility: String = row.try_get("visibility")?;

    if role.is_some() || visibility == "public_readonly" {
        Ok(role)
    } else {
        Ok(None)
    }
}

pub async fn require_workspace_access(
    pool: &PgPool,
    workspace_id: Uuid,
    user_id: Uuid,
) -> AppResult<Option<String>> {
    let role = workspace_role(pool, workspace_id, user_id).await?;
    if role.is_none() {
        return Err(AppError::forbidden("Workspace is not accessible for current user"));
    }
    Ok(role)
}

pub async fn require_workspace_admin(
    pool: &PgPool,
    workspace_id: Uuid,
    user_id: Uuid,
) -> AppResult<String> {
    let role = require_workspace_access(pool, workspace_id, user_id)
        .await?
        .ok_or_else(|| AppError::forbidden("Workspace admin access is required"))?;

    match role.as_str() {
        "owner" | "admin" => Ok(role),
        _ => Err(AppError::forbidden("Workspace admin access is required")),
    }
}

pub async fn require_workspace_owner(
    pool: &PgPool,
    workspace_id: Uuid,
    user_id: Uuid,
) -> AppResult<()> {
    let role = require_workspace_access(pool, workspace_id, user_id)
        .await?
        .ok_or_else(|| AppError::forbidden("Workspace owner access is required"))?;

    if role == "owner" {
        Ok(())
    } else {
        Err(AppError::forbidden("Workspace owner access is required"))
    }
}

pub async fn board_workspace_id(pool: &PgPool, board_id: Uuid) -> AppResult<Uuid> {
    sqlx::query_scalar::<_, Uuid>(
        r#"
        select workspace_id
        from boards
        where id = $1 and deleted_at is null
        "#,
    )
    .bind(board_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Board not found"))
}

pub async fn column_board_and_workspace_id(pool: &PgPool, column_id: Uuid) -> AppResult<(Uuid, Uuid)> {
    let row = sqlx::query(
        r#"
        select c.board_id, b.workspace_id
        from board_columns c
        join boards b on b.id = c.board_id
        where c.id = $1
          and c.deleted_at is null
          and b.deleted_at is null
        "#,
    )
    .bind(column_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Column not found"))?;

    Ok((row.try_get("board_id")?, row.try_get("workspace_id")?))
}

pub async fn card_board_and_workspace_id(pool: &PgPool, card_id: Uuid) -> AppResult<(Uuid, Uuid)> {
    let row = sqlx::query(
        r#"
        select c.board_id, b.workspace_id
        from cards c
        join boards b on b.id = c.board_id
        where c.id = $1
          and c.deleted_at is null
          and b.deleted_at is null
        "#,
    )
    .bind(card_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Card not found"))?;

    Ok((row.try_get("board_id")?, row.try_get("workspace_id")?))
}

pub async fn next_position_for_column(pool: &PgPool, board_id: Uuid) -> AppResult<f64> {
    let max_position = sqlx::query_scalar::<_, Option<f64>>(
        r#"
        select max(position::double precision)
        from board_columns
        where board_id = $1 and deleted_at is null
        "#,
    )
    .bind(board_id)
    .fetch_one(pool)
    .await?;

    Ok(max_position.unwrap_or(0.0) + POSITION_GAP)
}

pub async fn next_position_for_card(pool: &PgPool, board_id: Uuid, column_id: Uuid) -> AppResult<f64> {
    let max_position = sqlx::query_scalar::<_, Option<f64>>(
        r#"
        select max(position::double precision)
        from cards
        where board_id = $1 and column_id = $2 and deleted_at is null
        "#,
    )
    .bind(board_id)
    .bind(column_id)
    .fetch_one(pool)
    .await?;

    Ok(max_position.unwrap_or(0.0) + POSITION_GAP)
}
