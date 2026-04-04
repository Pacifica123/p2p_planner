use axum::Json;

use crate::error::AppResult;

use super::service;

pub async fn list_comments() -> AppResult<Json<serde_json::Value>> {
    service::list_comments().await?;
    unreachable!()
}

pub async fn create_comment() -> AppResult<Json<serde_json::Value>> {
    service::create_comment().await?;
    unreachable!()
}

pub async fn update_comment() -> AppResult<Json<serde_json::Value>> {
    service::update_comment().await?;
    unreachable!()
}

pub async fn delete_comment() -> AppResult<Json<serde_json::Value>> {
    service::delete_comment().await?;
    unreachable!()
}

