use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    state::AppState,
};

use super::{
    dto::{DevBootstrapUserRequest, DevBootstrapUserResponse},
    repo,
};

pub async fn sign_up() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_up is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_in() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_in is wired but business logic is not implemented yet",
    ))
}

pub async fn refresh() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.refresh is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_out() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_out is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_out_all() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_out_all is wired but business logic is not implemented yet",
    ))
}

fn ensure_dev_bootstrap_allowed(state: &AppState) -> AppResult<()> {
    match state.settings.app.env.to_ascii_lowercase().as_str() {
        "prod" | "production" => Err(AppError::not_found("Not found")),
        _ => Ok(()),
    }
}

pub async fn bootstrap_dev_user(
    state: &AppState,
    payload: DevBootstrapUserRequest,
) -> AppResult<DevBootstrapUserResponse> {
    ensure_dev_bootstrap_allowed(state)?;

    let user_id = match payload.user_id.as_deref() {
        Some(value) => Uuid::parse_str(value)
            .map_err(|_| AppError::bad_request("userId must be a valid UUID"))?,
        None => Uuid::now_v7(),
    };

    let email = payload
        .email
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| format!("smoke-{}@local.test", user_id));

    let display_name = payload
        .display_name
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "Smoke Test User".to_string());

    if !email.contains('@') {
        return Err(AppError::bad_request("email must look like an email address"));
    }

    repo::bootstrap_dev_user(&state.db, user_id, &email, &display_name).await
}
