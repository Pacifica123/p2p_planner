use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationProviderSummary {
    pub key: String,
    pub display_name: String,
    pub provider_type: String,
    pub status: String,
    pub auth_mode: String,
    pub supports_import: bool,
    pub supports_export: bool,
    pub supports_inbound_webhooks: bool,
    pub supports_outbound_webhooks: bool,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationTouchpoint {
    pub key: String,
    pub direction: String,
    pub payload_format: String,
    pub description: String,
    pub status: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct DomainEventSubscription {
    pub event_type: String,
    pub delivery_mode: String,
    pub purpose: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WebhookContract {
    pub mode: String,
    pub signature_scheme: String,
    pub event_types: Vec<String>,
    pub description: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationProviderDetailResponse {
    pub provider: IntegrationProviderSummary,
    pub import_touchpoints: Vec<IntegrationTouchpoint>,
    pub export_touchpoints: Vec<IntegrationTouchpoint>,
    pub domain_event_subscriptions: Vec<DomainEventSubscription>,
    pub inbound_webhook: Option<WebhookContract>,
    pub outbound_webhook: Option<WebhookContract>,
    pub boundary_rules: Vec<String>,
    pub notes: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationProviderCatalogResponse {
    pub items: Vec<IntegrationProviderSummary>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateImportJobRequest {
    pub provider_key: String,
    pub workspace_id: Option<String>,
    pub source_ref: Option<String>,
    #[serde(default)]
    pub options: Value,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateExportJobRequest {
    pub provider_key: String,
    pub workspace_id: Option<String>,
    pub target_ref: Option<String>,
    #[serde(default)]
    pub options: Value,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationOperationStubResponse {
    pub operation: String,
    pub provider_key: String,
    pub status: String,
    pub message: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WebhookReceiptResponse {
    pub provider_key: String,
    pub status: String,
    pub message: String,
    pub accepted_event_types: Vec<String>,
}
