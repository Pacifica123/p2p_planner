use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncStatusQuery {
    pub replica_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PullChangesQuery {
    pub replica_id: String,
    pub scope: Option<String>,
    pub workspace_id: Option<String>,
    pub last_server_order: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisterReplicaRequest {
    pub replica_key: String,
    pub kind: Option<String>,
    pub display_name: Option<String>,
    pub platform: Option<String>,
    pub protocol_version: Option<String>,
    pub app_version: Option<String>,
    pub metadata: Option<Value>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ReplicaResponse {
    pub id: String,
    pub replica_key: Option<String>,
    pub kind: String,
    pub status: String,
    pub user_id: Option<String>,
    pub device_id: Option<String>,
    pub display_name: Option<String>,
    pub platform: Option<String>,
    pub protocol_version: Option<String>,
    pub app_version: Option<String>,
    pub last_seen_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisterReplicaResponse {
    pub replica: ReplicaResponse,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReplicaListResponse {
    pub items: Vec<ReplicaResponse>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncStatusResponse {
    pub healthy: bool,
    pub mode: String,
    pub server_time: String,
    pub max_server_order: Option<i64>,
    pub replica: Option<ReplicaResponse>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncScopeRequest {
    pub scope: String,
    pub workspace_id: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncScopeResponse {
    pub scope: String,
    pub workspace_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClientChangeEvent {
    pub event_id: String,
    pub replica_id: String,
    pub replica_seq: i64,
    pub entity_type: String,
    pub entity_id: String,
    pub operation: String,
    pub field_mask: Option<Vec<String>>,
    pub logical_clock: i64,
    pub base_server_order: Option<i64>,
    pub occurred_at: Option<String>,
    #[serde(default)]
    pub payload: Value,
    #[serde(default)]
    pub metadata: Value,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ServerChangeEvent {
    pub event_id: String,
    pub replica_id: String,
    pub replica_seq: i64,
    pub entity_type: String,
    pub entity_id: String,
    pub operation: String,
    pub field_mask: Vec<String>,
    pub logical_clock: i64,
    pub base_server_order: Option<i64>,
    pub payload: Value,
    pub metadata: Value,
    pub server_order: i64,
    pub accepted_at: String,
    pub actor_user_id: Option<String>,
    pub actor_device_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PushChangesRequest {
    pub replica_id: String,
    pub workspace_id: Option<String>,
    pub events: Vec<ClientChangeEvent>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PushEventResult {
    pub event_id: String,
    pub replica_seq: i64,
    pub status: String,
    pub server_order: Option<i64>,
    pub error: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PushChangesResponse {
    pub results: Vec<PushEventResult>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncCursorResponse {
    pub scope: SyncScopeResponse,
    pub replica_id: String,
    pub last_server_order: i64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PullChangesResponse {
    pub events: Vec<ServerChangeEvent>,
    pub next_cursor: SyncCursorResponse,
    pub has_more: bool,
}
