use p2p_kanban_sync_core::validate_client_event;
use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    modules::common::{board_workspace_id, require_workspace_admin, AuthContext},
    state::AppState,
};

use super::dto::{
    ClientChangeEvent, CreateRoamingCapabilityRequest, PullChangesQuery, PullChangesResponse,
    PushChangesRequest, PushChangesResponse, RegisterReplicaRequest, RegisterReplicaResponse,
    ReplicaListResponse, RoamingCapabilityResponse, SyncStatusQuery, SyncStatusResponse,
    TransportAdapterStatus, TransportStatusResponse,
};

const MAX_PUSH_EVENTS: usize = 500;
const DEFAULT_PULL_LIMIT: i64 = 100;
const MAX_PULL_LIMIT: i64 = 1000;

pub async fn create_roaming_capability(
    state: &AppState,
    auth: AuthContext,
    payload: CreateRoamingCapabilityRequest,
) -> AppResult<RoamingCapabilityResponse> {
    #[cfg(not(feature = "nostr-shadow"))]
    {
        let _ = (state, auth, payload);
        return Err(AppError::conflict(
            "This backend build does not include independent board sync",
        ));
    }

    #[cfg(feature = "nostr-shadow")]
    {
        let nostr = &state.settings.transports.nostr;
        if !nostr.enabled {
            return Err(AppError::conflict(
                "Independent board sync is not enabled on this node",
            ));
        }

        let workspace_id = board_workspace_id(&state.db, payload.board_id).await?;
        require_workspace_admin(&state.db, workspace_id, auth.user_id).await?;
        let imported = sqlx::query_as::<_, (String, String)>(
            r#"
            select board_tag, board_key_base64
            from roaming_board_capabilities
            where board_id = $1
            "#,
        )
        .bind(payload.board_id)
        .fetch_optional(&state.db)
        .await?;
        let material = if let Some((board_tag, board_key)) = imported {
            let material =
                p2p_kanban_nostr_transport::NostrCodec::roaming_capability_from_board_key(
                    &payload.board_id.to_string(),
                    &board_key,
                )
                .map_err(|_| AppError::internal())?;
            if material.board_tag != board_tag {
                return Err(AppError::internal());
            }
            material
        } else {
            let master_key = nostr.master_key().map_err(|_| AppError::internal())?;
            let codec = p2p_kanban_nostr_transport::NostrCodec::new(master_key)
                .map_err(|_| AppError::internal())?;
            codec
                .roaming_capability(&payload.board_id.to_string())
                .map_err(|_| AppError::internal())?
        };
        let provisioned_at = sqlx::query_scalar::<_, String>(
            r#"select to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')"#,
        )
        .fetch_one(&state.db)
        .await?;

        Ok(RoamingCapabilityResponse {
            format_version: 1,
            protocol_version: material.protocol_version,
            workspace_id: workspace_id.to_string(),
            board_id: payload.board_id.to_string(),
            board_tag: material.board_tag,
            board_key: material.board_key,
            relays: nostr.relays.clone(),
            event_kind: nostr
                .event_kind
                .saturating_add(p2p_kanban_nostr_transport::ROAMING_EVENT_KIND_OFFSET),
            minimum_relay_acks: nostr.min_relay_acks,
            provisioned_at,
        })
    }
}

fn parse_uuid(value: &str, field: &str) -> AppResult<Uuid> {
    Uuid::parse_str(value)
        .map_err(|_| AppError::bad_request(format!("{field} must be a valid UUID")))
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

fn requires_workspace_scope(entity_type: &str) -> bool {
    !matches!(entity_type, "workspace")
}

fn validate_workspace_scoping(
    workspace_id: Option<Uuid>,
    event: &ClientChangeEvent,
) -> AppResult<()> {
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
    validate_client_event(event).map_err(|error| AppError::bad_request(error.to_string()))
}

pub async fn get_status(
    state: &AppState,
    auth: AuthContext,
    query: SyncStatusQuery,
) -> AppResult<SyncStatusResponse> {
    let replica_id = query
        .replica_id
        .as_deref()
        .map(|id| parse_uuid(id, "replicaId"))
        .transpose()?;
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
    let workspace_id = payload
        .workspace_id
        .as_deref()
        .map(|id| parse_uuid(id, "workspaceId"))
        .transpose()?;
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
            return Err(AppError::bad_request(
                "All events must belong to request replicaId",
            ));
        }
        if let Some(previous_seq) = previous_seq {
            if event.replica_seq <= previous_seq {
                return Err(AppError::bad_request(
                    "events must be sorted by monotonically increasing replicaSeq",
                ));
            }
        }
        previous_seq = Some(event.replica_seq);
    }

    super::repo::push_changes(
        &state.db,
        auth,
        replica_id,
        workspace_id,
        payload.events,
        state.settings.transports.nostr.enabled,
    )
    .await
}

pub async fn pull_changes(
    state: &AppState,
    auth: AuthContext,
    query: PullChangesQuery,
) -> AppResult<PullChangesResponse> {
    let replica_id = parse_uuid(&query.replica_id, "replicaId")?;
    let scope = normalize_scope(query.scope)?;
    let workspace_id = query
        .workspace_id
        .as_deref()
        .map(|id| parse_uuid(id, "workspaceId"))
        .transpose()?;
    if scope == "workspace" && workspace_id.is_none() {
        return Err(AppError::bad_request(
            "workspaceId is required for workspace sync scope",
        ));
    }
    if scope == "global" && workspace_id.is_some() {
        return Err(AppError::bad_request(
            "workspaceId is only valid for workspace sync scope",
        ));
    }
    let last_server_order = query.last_server_order.unwrap_or(0).max(0);
    let limit = query
        .limit
        .unwrap_or(DEFAULT_PULL_LIMIT)
        .clamp(1, MAX_PULL_LIMIT);

    super::repo::pull_changes(
        &state.db,
        auth,
        replica_id,
        scope,
        workspace_id,
        last_server_order,
        limit,
    )
    .await
}

pub async fn get_transport_status(
    state: &AppState,
    _auth: AuthContext,
) -> AppResult<TransportStatusResponse> {
    let queue = crate::transports::transport_queue_status(&state.db).await?;
    Ok(TransportStatusResponse {
        coordinator: TransportAdapterStatus {
            enabled: true,
            mode: "canonical".to_string(),
            configured_endpoints: 1,
        },
        nostr: TransportAdapterStatus {
            enabled: state.settings.transports.nostr.enabled,
            mode: "shadow_store_and_forward".to_string(),
            configured_endpoints: state.settings.transports.nostr.relays.len(),
        },
        iroh: TransportAdapterStatus {
            enabled: state.settings.transports.iroh.enabled,
            mode: "direct_fast_path".to_string(),
            configured_endpoints: state.settings.transports.iroh.peers.len(),
        },
        queue,
    })
}
