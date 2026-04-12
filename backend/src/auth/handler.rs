use axum::{extract::State, Json};

use crate::{
    error::AppResult,
    http::response::{ok, ApiEnvelope},
    state::AppState,
};

use super::{
    dto::{DevBootstrapUserRequest, DevBootstrapUserResponse, SessionResponse},
    service,
};

pub async fn sign_up() -> AppResult<Json<serde_json::Value>> {
    service::sign_up().await?;
    unreachable!()
}

pub async fn sign_in() -> AppResult<Json<serde_json::Value>> {
    service::sign_in().await?;
    unreachable!()
}

pub async fn refresh() -> AppResult<Json<serde_json::Value>> {
    service::refresh().await?;
    unreachable!()
}

pub async fn sign_out() -> AppResult<Json<serde_json::Value>> {
    service::sign_out().await?;
    unreachable!()
}

pub async fn sign_out_all() -> AppResult<Json<serde_json::Value>> {
    service::sign_out_all().await?;
    unreachable!()
}

pub async fn bootstrap_dev_user(
    State(state): State<AppState>,
    Json(payload): Json<DevBootstrapUserRequest>,
) -> AppResult<Json<ApiEnvelope<DevBootstrapUserResponse>>> {
    let user = service::bootstrap_dev_user(&state, payload).await?;
    Ok(ok(user))
}

pub async fn get_session() -> AppResult<Json<ApiEnvelope<SessionResponse>>> {
    Ok(ok(SessionResponse {
        authenticated: false,
        mode: "skeleton",
    }))
}
