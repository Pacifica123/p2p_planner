use axum::Json;

use crate::error::AppResult;

use super::service;

pub async fn get_current_user() -> AppResult<Json<serde_json::Value>> {
    service::get_current_user().await?;
    unreachable!()
}

pub async fn list_devices() -> AppResult<Json<serde_json::Value>> {
    service::list_devices().await?;
    unreachable!()
}

pub async fn revoke_device() -> AppResult<Json<serde_json::Value>> {
    service::revoke_device().await?;
    unreachable!()
}

