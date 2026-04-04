use serde::Serialize;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncStatusResponse { pub status: String, pub mode: String }

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReplicaResponse { pub id: String, pub display_name: String, pub protocol_version: Option<String> }
