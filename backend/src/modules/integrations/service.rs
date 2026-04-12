use serde_json::Value;
use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    modules::common::{board_workspace_id, ensure_user_exists, require_workspace_access},
    state::AppState,
};

use super::dto::{
    CreateExportJobRequest, CreateImportExecutionRequest, CreateImportJobRequest,
    CreateImportPreviewRequest, CreatePortableExportRequest, ImportExecutionResponse,
    ImportExportCapabilitiesResponse, ImportPreviewResponse, IntegrationOperationStubResponse,
    IntegrationProviderCatalogResponse, IntegrationProviderDetailResponse, PortableBundleManifest,
    PortableBundleSummary, PortableEntityCounts, PortableExportResponse, WebhookReceiptResponse,
};

const IMPORT_EXPORT_PROVIDER_KEY: &str = "import_export";
const PORTABLE_BUNDLE_FORMAT: &str = "p2p_planner_bundle";
const PORTABLE_BUNDLE_FORMAT_VERSION: i32 = 1;

fn ensure_provider_exists(provider_key: &str) -> AppResult<IntegrationProviderDetailResponse> {
    super::provider::find_provider(provider_key).ok_or_else(|| {
        AppError::not_found(format!("Integration provider '{provider_key}' not found"))
    })
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

pub async fn get_import_export_capabilities(
    state: &AppState,
    actor_user_id: Uuid,
) -> AppResult<ImportExportCapabilitiesResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    ensure_provider_exists(IMPORT_EXPORT_PROVIDER_KEY)?;

    Ok(ImportExportCapabilitiesResponse {
        provider_key: IMPORT_EXPORT_PROVIDER_KEY.to_string(),
        format: PORTABLE_BUNDLE_FORMAT.to_string(),
        format_version: PORTABLE_BUNDLE_FORMAT_VERSION,
        supported_export_modes: vec![
            "portable_export".to_string(),
            "backup_snapshot".to_string(),
        ],
        client_only_backup_modes: vec!["local_backup_snapshot".to_string()],
        supported_import_modes: vec![
            "portable_import".to_string(),
            "restore_backup".to_string(),
        ],
        supported_scope_kinds: vec!["workspace".to_string(), "board".to_string()],
        supported_restore_strategies: vec!["create_copy".to_string(), "merge_review".to_string()],
        max_bundle_size_bytes: None,
        notes: vec![
            "Portable export and coordinated backup use the same versioned bundle contract but different intent and defaults.".to_string(),
            "Local backup snapshot is a client-owned offline flow and may include unsynced local-first state.".to_string(),
            "Current backend implementation exposes contracts and stub responses, not file packaging or real restore execution.".to_string(),
        ],
    })
}

pub async fn create_portable_export(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreatePortableExportRequest,
) -> AppResult<PortableExportResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    ensure_provider_exists(IMPORT_EXPORT_PROVIDER_KEY)?;

    validate_export_mode(&payload.export_mode)?;
    validate_scope_kind(&payload.scope_kind)?;

    let (workspace_id, board_id) = resolve_export_scope_access(
        state,
        actor_user_id,
        &payload.scope_kind,
        payload.workspace_id,
        payload.board_id,
    )
    .await?;

    let summary = build_summary(
        &payload.scope_kind,
        payload.include_activity_history,
        payload.include_appearance,
        payload.include_archived,
        payload.include_attachments,
    );

    let manifest = PortableBundleManifest {
        format: PORTABLE_BUNDLE_FORMAT.to_string(),
        format_version: PORTABLE_BUNDLE_FORMAT_VERSION,
        bundle_kind: payload.export_mode.clone(),
        scope_kind: payload.scope_kind.clone(),
        workspace_id,
        board_id,
        includes_local_metadata: false,
        summary: summary.clone(),
    };

    let job_id = Uuid::now_v7();
    let scope_suffix = if let Some(board_id) = board_id {
        format!("board-{board_id}")
    } else if let Some(workspace_id) = workspace_id {
        format!("workspace-{workspace_id}")
    } else {
        payload.scope_kind.clone()
    };
    let suggested_file_name = format!(
        "p2p-planner-{}-{}-{}.bundle.json",
        payload.export_mode.replace('_', "-"),
        scope_suffix,
        job_id
    );

    let mut warnings = Vec::new();
    if payload.include_activity_history {
        warnings.push(
            "Activity history inclusion is part of the bundle contract, but full history serialization is not implemented yet.".to_string(),
        );
    }
    if payload.include_attachments {
        warnings.push(
            "Attachments are reserved in the bundle manifest, but blob export is not implemented yet.".to_string(),
        );
    }

    Ok(PortableExportResponse {
        job_id,
        provider_key: IMPORT_EXPORT_PROVIDER_KEY.to_string(),
        status: "ready_stub".to_string(),
        export_mode: payload.export_mode,
        suggested_file_name,
        target_ref: payload.target_ref,
        bundle_manifest: manifest,
        message: "Portable export contract is ready. The current backend returns a manifest-oriented stub response instead of streaming a real bundle file.".to_string(),
        warnings,
    })
}

pub async fn preview_import_bundle(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreateImportPreviewRequest,
) -> AppResult<ImportPreviewResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    ensure_provider_exists(IMPORT_EXPORT_PROVIDER_KEY)?;

    validate_import_mode(&payload.import_mode)?;
    validate_restore_strategy(&payload.restore_strategy)?;
    validate_json_object(&payload.bundle_manifest, "bundleManifest")?;
    validate_json_object(&payload.options, "options")?;

    if let Some(target_workspace_id) = payload.target_workspace_id {
        require_workspace_access(&state.db, target_workspace_id, actor_user_id).await?;
    }

    let requires_manual_review = payload.restore_strategy == "merge_review";
    let mut warnings = vec![
        "Preview is contract-level for now: the backend validates mode/strategy and returns a stable review surface, but does not inspect a real uploaded file yet.".to_string(),
    ];
    if payload.target_workspace_id.is_some() {
        warnings.push(
            "Targeting an existing workspace implies collision review for names, lifecycle state and future field-level conflicts.".to_string(),
        );
    }

    Ok(ImportPreviewResponse {
        preview_id: Uuid::now_v7(),
        provider_key: IMPORT_EXPORT_PROVIDER_KEY.to_string(),
        status: "preview_stub".to_string(),
        detected_format: PORTABLE_BUNDLE_FORMAT.to_string(),
        detected_format_version: PORTABLE_BUNDLE_FORMAT_VERSION,
        import_mode: payload.import_mode,
        restore_strategy: payload.restore_strategy,
        requires_manual_review,
        warnings,
        steps: vec![
            "Read bundle manifest and compatibility metadata".to_string(),
            "Build restore plan with create-copy or merge-review strategy".to_string(),
            "Apply validated domain commands instead of raw table writes".to_string(),
        ],
        summary: build_summary("workspace", true, true, true, false),
    })
}

pub async fn create_import_execution(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreateImportExecutionRequest,
) -> AppResult<ImportExecutionResponse> {
    ensure_user_exists(&state.db, actor_user_id).await?;
    ensure_provider_exists(IMPORT_EXPORT_PROVIDER_KEY)?;

    validate_import_mode(&payload.import_mode)?;
    validate_restore_strategy(&payload.restore_strategy)?;
    validate_json_object(&payload.bundle_manifest, "bundleManifest")?;
    validate_json_object(&payload.options, "options")?;

    if let Some(target_workspace_id) = payload.target_workspace_id {
        require_workspace_access(&state.db, target_workspace_id, actor_user_id).await?;
    }

    Ok(ImportExecutionResponse {
        job_id: Uuid::now_v7(),
        provider_key: IMPORT_EXPORT_PROVIDER_KEY.to_string(),
        status: "accepted_stub".to_string(),
        import_mode: payload.import_mode,
        restore_strategy: payload.restore_strategy,
        preview_id: payload.preview_id,
        target_workspace_id: payload.target_workspace_id,
        message: "Import/restore execution contract is reserved. The current backend accepts the request shape and returns a stable stub instead of mutating domain state.".to_string(),
        warnings: vec![
            "Real bundle parsing, apply planning and mutation execution are future work.".to_string(),
        ],
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

fn validate_export_mode(value: &str) -> AppResult<()> {
    match value {
        "portable_export" | "backup_snapshot" => Ok(()),
        _ => Err(AppError::bad_request(
            "exportMode has unsupported value; expected portable_export or backup_snapshot",
        )),
    }
}

fn validate_import_mode(value: &str) -> AppResult<()> {
    match value {
        "portable_import" | "restore_backup" => Ok(()),
        _ => Err(AppError::bad_request(
            "importMode has unsupported value; expected portable_import or restore_backup",
        )),
    }
}

fn validate_restore_strategy(value: &str) -> AppResult<()> {
    match value {
        "create_copy" | "merge_review" => Ok(()),
        _ => Err(AppError::bad_request(
            "restoreStrategy has unsupported value; expected create_copy or merge_review",
        )),
    }
}

fn validate_scope_kind(value: &str) -> AppResult<()> {
    match value {
        "workspace" | "board" => Ok(()),
        _ => Err(AppError::bad_request(
            "scopeKind has unsupported value; expected workspace or board",
        )),
    }
}

async fn resolve_export_scope_access(
    state: &AppState,
    actor_user_id: Uuid,
    scope_kind: &str,
    workspace_id: Option<Uuid>,
    board_id: Option<Uuid>,
) -> AppResult<(Option<Uuid>, Option<Uuid>)> {
    match scope_kind {
        "workspace" => {
            let workspace_id = workspace_id
                .ok_or_else(|| AppError::bad_request("workspaceId is required when scopeKind=workspace"))?;
            require_workspace_access(&state.db, workspace_id, actor_user_id).await?;
            Ok((Some(workspace_id), None))
        }
        "board" => {
            let board_id = board_id
                .ok_or_else(|| AppError::bad_request("boardId is required when scopeKind=board"))?;
            let workspace_id = board_workspace_id(&state.db, board_id).await?;
            require_workspace_access(&state.db, workspace_id, actor_user_id).await?;
            Ok((Some(workspace_id), Some(board_id)))
        }
        _ => Err(AppError::bad_request(
            "scopeKind has unsupported value; expected workspace or board",
        )),
    }
}

fn build_summary(
    scope_kind: &str,
    includes_activity_history: bool,
    includes_appearance: bool,
    includes_archived: bool,
    includes_attachments: bool,
) -> PortableBundleSummary {
    let entity_counts = match scope_kind {
        "board" => PortableEntityCounts {
            workspaces: 0,
            boards: 1,
            columns: 3,
            cards: 12,
            comments: 0,
            checklists: 0,
            attachments: 0,
        },
        _ => PortableEntityCounts {
            workspaces: 1,
            boards: 2,
            columns: 6,
            cards: 24,
            comments: 0,
            checklists: 0,
            attachments: 0,
        },
    };

    PortableBundleSummary {
        scope_kind: scope_kind.to_string(),
        entity_counts,
        includes_activity_history,
        includes_appearance,
        includes_archived,
        includes_attachments,
    }
}
