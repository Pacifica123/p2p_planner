use axum::Json;

use crate::error::AppResult;

use super::service;

pub async fn list_labels() -> AppResult<Json<serde_json::Value>> {
    service::list_labels().await?;
    unreachable!()
}

pub async fn create_label() -> AppResult<Json<serde_json::Value>> {
    service::create_label().await?;
    unreachable!()
}

pub async fn update_label() -> AppResult<Json<serde_json::Value>> {
    service::update_label().await?;
    unreachable!()
}

pub async fn delete_label() -> AppResult<Json<serde_json::Value>> {
    service::delete_label().await?;
    unreachable!()
}

pub async fn replace_card_labels() -> AppResult<Json<serde_json::Value>> {
    service::replace_card_labels().await?;
    unreachable!()
}

