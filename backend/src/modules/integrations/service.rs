use serde_json::Value;
use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    modules::common::ensure_user_exists,
    state::AppState,
};

use super::dto::{
    CreateExportJobRequest, CreateImportJobRequest, IntegrationOperationStubResponse,
    IntegrationProviderCatalogResponse, IntegrationProviderDetailResponse, WebhookReceiptResponse,
};

fn ensure_provider_exists(provider_key: &str) -> AppResult<IntegrationProviderDetailResponse> {
    super::provider::find_provider(provider_key)
        .ok_or_else(|| AppError::not_found(format!("Integration provider '{provider_key}' not found")))
}

pub async fn list_providers(
    state: &AppState,
    actor_user_id: Uuid,
) -> AppResult<IntegrationProviderCatalogResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;

    let items = super::provider::builtin_providers()
        .into_iter()
        .map(|provider| provider.manifest().provider)
        .collect();

    Ok(IntegrationProviderCatalogResponse { items })
}

pub async fn get_provider_detail(
    state: &AppState,
    actor_user_id: Uuid,
    provider_key: &str,
) -> AppResult<IntegrationProviderDetailResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    ensure_provider_exists(provider_key)
}

pub async fn create_import_job(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreateImportJobRequest,
) -> AppResult<IntegrationOperationStubResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    let provider = ensure_provider_exists(&payload.provider_key)?;

    validate_json_object(&payload.options, "options")?;

    Ok(IntegrationOperationStubResponse {
        operation: "import_job.create".to_string(),
        provider_key: provider.provider.key,
        status: "stub_only".to_string(),
        message: "Import orchestration contract is reserved, but concrete provider execution is not implemented yet.".to_string(),
    })
}

pub async fn create_export_job(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreateExportJobRequest,
) -> AppResult<IntegrationOperationStubResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    let provider = ensure_provider_exists(&payload.provider_key)?;

    validate_json_object(&payload.options, "options")?;

    Ok(IntegrationOperationStubResponse {
        operation: "export_job.create".to_string(),
        provider_key: provider.provider.key,
        status: "stub_only".to_string(),
        message: "Export orchestration contract is reserved, but concrete provider execution is not implemented yet.".to_string(),
    })
}

pub async fn receive_webhook(provider_key: &str) -> AppResult<WebhookReceiptResponse> {
    let provider = ensure_provider_exists(provider_key)?;

    let accepted_event_types = provider
        .inbound_webhook
        .as_ref()
        .map(|contract| contract.event_types.clone())
        .unwrap_or_default();

    Ok(WebhookReceiptResponse {
        provider_key: provider.provider.key,
        status: "stub_only".to_string(),
        message: "Webhook boundary is reserved, but signature verification and command translation are not implemented yet.".to_string(),
        accepted_event_types,
    })
}

fn validate_json_object(value: &Value, field_name: &str) -> AppResult<()> {
    if value.is_null() || value.is_object() {
        Ok(())
    } else {
        Err(AppError::bad_request(format!("{field_name} must be a JSON object")))
    }
}
