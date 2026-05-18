use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    modules::common::AuthContext,
    state::AppState,
};

use super::dto::{
    ClientChangeEvent, PullChangesQuery, PullChangesResponse, PushChangesRequest, PushChangesResponse,
    RegisterReplicaRequest, RegisterReplicaResponse, ReplicaListResponse, SyncStatusQuery, SyncStatusResponse,
};

const MAX_PUSH_EVENTS: usize = 500;
const DEFAULT_PULL_LIMIT: i64 = 100;
const MAX_PULL_LIMIT: i64 = 1000;

fn parse_uuid(value: &str, field: &str) -> AppResult<Uuid> {
    Uuid::parse_str(value).map_err(|_| AppError::bad_request(format!("{field} must be a valid UUID")))
}

fn normalize_scope(scope: Option<String>) -> AppResult<String> {
    let scope = scope.unwrap_or_else(|| "global".to_string());
    match scope.as_str() {
        "global" | "workspace" => Ok(scope),
        _ => Err(AppError::bad_request("Unsupported sync scope")),
    }
}

fn normalize_replica_kind(kind: Option<String>) -> AppResult<String> {
    let kind = kind.unwrap_or_else(|| "browser_profile".to_string());
    match kind.as_str() {
        "device" | "browser_profile" | "client" => Ok("client".to_string()),
        "import_worker" | "import" => Ok("import".to_string()),
        "server" => Ok("server".to_string()),
        _ => Err(AppError::bad_request("Unsupported replica kind")),
    }
}

fn validate_operation(operation: &str) -> AppResult<&'static str> {
    match operation {
        "create" => Ok("create"),
        "update" | "move" | "complete" => Ok("update"),
        "delete" => Ok("delete"),
        "restore" => Ok("restore"),
        "reorder" => Ok("reorder"),
        "add" => Ok("add"),
        "remove" => Ok("remove"),
        "archive" => Ok("archive"),
        "unarchive" => Ok("unarchive"),
        _ => Err(AppError::bad_request("Unsupported sync event operation")),
    }
}

fn validate_entity_type(entity_type: &str) -> AppResult<()> {
    match entity_type {
        "workspace" | "workspace_member" | "board" | "column" | "card" | "board_label" | "card_label"
        | "checklist" | "checklist_item" | "comment" => Ok(()),
        _ => Err(AppError::bad_request("Unsupported sync event entityType")),
    }
}

fn requires_workspace_scope(entity_type: &str) -> bool {
    !matches!(entity_type, "workspace")
}

fn validate_workspace_scoping(workspace_id: Option<Uuid>, event: &ClientChangeEvent) -> AppResult<()> {
    if workspace_id.is_none() && requires_workspace_scope(&event.entity_type) {
        return Err(AppError::bad_request(
            "workspaceId is required for workspace-scoped sync events",
        ));
    }

    if let Some(workspace_id) = workspace_id {
        if event.entity_type == "workspace" {
            let entity_id = parse_uuid(&event.entity_id, "entityId")?;
            if entity_id != workspace_id {
                return Err(AppError::bad_request(
                    "workspace sync event entityId must match request workspaceId",
                ));
            }
        }
    }

    Ok(())
}

fn validate_event_shape(event: &ClientChangeEvent) -> AppResult<()> {
    parse_uuid(&event.event_id, "eventId")?;
    parse_uuid(&event.replica_id, "event.replicaId")?;
    parse_uuid(&event.entity_id, "entityId")?;
    if event.replica_seq < 1 {
        return Err(AppError::bad_request("replicaSeq must be positive"));
    }
    if event.logical_clock < 1 {
        return Err(AppError::bad_request("logicalClock must be positive"));
    }
    validate_entity_type(&event.entity_type)?;
    validate_operation(&event.operation)?;
    Ok(())
}

pub async fn get_status(
    state: &AppState,
    auth: AuthContext,
    query: SyncStatusQuery,
) -> AppResult<SyncStatusResponse> {
    let replica_id = query.replica_id.as_deref().map(|id| parse_uuid(id, "replicaId")).transpose()?;
    super::repo::get_status(&state.db, auth, replica_id).await
}

pub async fn list_replicas(state: &AppState, auth: AuthContext) -> AppResult<ReplicaListResponse> {
    super::repo::list_replicas(&state.db, auth).await
}

pub async fn register_replica(
    state: &AppState,
    auth: AuthContext,
    mut payload: RegisterReplicaRequest,
) -> AppResult<RegisterReplicaResponse> {
    payload.replica_key = payload.replica_key.trim().to_string();
    if payload.replica_key.is_empty() {
        return Err(AppError::bad_request("replicaKey is required"));
    }
    if payload.replica_key.len() > 160 {
        return Err(AppError::bad_request("replicaKey is too long"));
    }
    let kind = normalize_replica_kind(payload.kind.clone())?;
    super::repo::register_replica(&state.db, auth, payload, kind).await
}

pub async fn push_changes(
    state: &AppState,
    auth: AuthContext,
    payload: PushChangesRequest,
) -> AppResult<PushChangesResponse> {
    let replica_id = parse_uuid(&payload.replica_id, "replicaId")?;
    let workspace_id = payload.workspace_id.as_deref().map(|id| parse_uuid(id, "workspaceId")).transpose()?;
    if payload.events.is_empty() {
        return Err(AppError::bad_request("At least one sync event is required"));
    }
    if payload.events.len() > MAX_PUSH_EVENTS {
        return Err(AppError::bad_request("Too many sync events in one push"));
    }

    let mut previous_seq: Option<i64> = None;
    for event in &payload.events {
        validate_event_shape(event)?;
        validate_workspace_scoping(workspace_id, event)?;
        let event_replica_id = parse_uuid(&event.replica_id, "event.replicaId")?;
        if event_replica_id != replica_id {
            return Err(AppError::bad_request("All events must belong to request replicaId"));
        }
        if let Some(previous_seq) = previous_seq {
            if event.replica_seq <= previous_seq {
                return Err(AppError::bad_request("events must be sorted by monotonically increasing replicaSeq"));
            }
        }
        previous_seq = Some(event.replica_seq);
    }

    super::repo::push_changes(&state.db, auth, replica_id, workspace_id, payload.events).await
}

pub async fn pull_changes(
    state: &AppState,
    auth: AuthContext,
    query: PullChangesQuery,
) -> AppResult<PullChangesResponse> {
    let replica_id = parse_uuid(&query.replica_id, "replicaId")?;
    let scope = normalize_scope(query.scope)?;
    let workspace_id = query.workspace_id.as_deref().map(|id| parse_uuid(id, "workspaceId")).transpose()?;
    if scope == "workspace" && workspace_id.is_none() {
        return Err(AppError::bad_request("workspaceId is required for workspace sync scope"));
    }
    if scope == "global" && workspace_id.is_some() {
        return Err(AppError::bad_request("workspaceId is only valid for workspace sync scope"));
    }
    let last_server_order = query.last_server_order.unwrap_or(0).max(0);
    let limit = query.limit.unwrap_or(DEFAULT_PULL_LIMIT).clamp(1, MAX_PULL_LIMIT);

    super::repo::pull_changes(&state.db, auth, replica_id, scope, workspace_id, last_server_order, limit).await
}
