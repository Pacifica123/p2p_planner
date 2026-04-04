use axum::Json;

use crate::error::AppResult;

use super::service;

pub async fn get_status() -> AppResult<Json<serde_json::Value>> {
    service::get_status().await?;
    unreachable!()
}

pub async fn list_replicas() -> AppResult<Json<serde_json::Value>> {
    service::list_replicas().await?;
    unreachable!()
}

pub async fn register_replica() -> AppResult<Json<serde_json::Value>> {
    service::register_replica().await?;
    unreachable!()
}

pub async fn push_changes() -> AppResult<Json<serde_json::Value>> {
    service::push_changes().await?;
    unreachable!()
}

pub async fn pull_changes() -> AppResult<Json<serde_json::Value>> {
    service::pull_changes().await?;
    unreachable!()
}

