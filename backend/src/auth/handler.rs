use axum::Json;

use crate::{
    error::AppResult,
    http::response::ok,
};

use super::{dto::SessionResponse, service};

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

pub async fn get_session() -> AppResult<Json<crate::http::response::ApiEnvelope<SessionResponse>>> {
    Ok(ok(SessionResponse {
        authenticated: false,
        mode: "skeleton",
    }))
}
