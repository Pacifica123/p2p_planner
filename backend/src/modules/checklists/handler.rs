use axum::Json;

use crate::error::AppResult;

use super::service;

pub async fn list_checklists() -> AppResult<Json<serde_json::Value>> {
    service::list_checklists().await?;
    unreachable!()
}

pub async fn create_checklist() -> AppResult<Json<serde_json::Value>> {
    service::create_checklist().await?;
    unreachable!()
}

pub async fn update_checklist() -> AppResult<Json<serde_json::Value>> {
    service::update_checklist().await?;
    unreachable!()
}

pub async fn delete_checklist() -> AppResult<Json<serde_json::Value>> {
    service::delete_checklist().await?;
    unreachable!()
}

pub async fn create_item() -> AppResult<Json<serde_json::Value>> {
    service::create_item().await?;
    unreachable!()
}

pub async fn update_item() -> AppResult<Json<serde_json::Value>> {
    service::update_item().await?;
    unreachable!()
}

pub async fn delete_item() -> AppResult<Json<serde_json::Value>> {
    service::delete_item().await?;
    unreachable!()
}

