use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    Json,
};
use serde_json::Value;

use crate::{
    error::AppResult,
    http::response::ok,
    modules::common::actor_user_id,
    state::AppState,
};

use super::{
    dto::{CreateExportJobRequest, CreateImportJobRequest},
    service,
};

pub async fn list_providers(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> AppResult<impl IntoResponse> {
    let actor = actor_user_id(&headers)?;
    let response = service::list_providers(&state, actor).await?;
    Ok(ok(response))
}

pub async fn get_provider_detail(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(provider_key): Path<String>,
) -> AppResult<impl IntoResponse> {
    let actor = actor_user_id(&headers)?;
    let response = service::get_provider_detail(&state, actor, &provider_key).await?;
    Ok(ok(response))
}

pub async fn create_import_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CreateImportJobRequest>,
) -> AppResult<impl IntoResponse> {
    let actor = actor_user_id(&headers)?;
    let response = service::create_import_job(&state, actor, payload).await?;
    Ok((StatusCode::ACCEPTED, ok(response)))
}

pub async fn create_export_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CreateExportJobRequest>,
) -> AppResult<impl IntoResponse> {
    let actor = actor_user_id(&headers)?;
    let response = service::create_export_job(&state, actor, payload).await?;
    Ok((StatusCode::ACCEPTED, ok(response)))
}

pub async fn receive_webhook(
    Path(provider_key): Path<String>,
    Json(_payload): Json<Value>,
) -> AppResult<impl IntoResponse> {
    let response = service::receive_webhook(&provider_key).await?;
    Ok((StatusCode::ACCEPTED, ok(response)))
}
