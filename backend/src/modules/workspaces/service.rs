use uuid::Uuid;

use crate::{error::{AppError, AppResult}, state::AppState};

use super::dto::{
    AddWorkspaceMemberRequest, CreateWorkspaceRequest, ListWorkspacesQuery, UpdateWorkspaceMemberRequest,
    UpdateWorkspaceRequest, WorkspaceListResponse, WorkspaceMemberResponse, WorkspaceMembersListResponse,
    WorkspaceResponse, WorkspaceWithMembersResponse,
};

pub async fn list_workspaces(
    state: &AppState,
    actor_user_id: Uuid,
    query: ListWorkspacesQuery,
) -> AppResult<WorkspaceListResponse> {
    super::repo::list_workspaces(&state.db, actor_user_id, query).await
}

pub async fn create_workspace(
    state: &AppState,
    actor_user_id: Uuid,
    payload: CreateWorkspaceRequest,
) -> AppResult<WorkspaceResponse> {
    let name = payload.name.trim();
    if name.is_empty() {
        return Err(AppError::bad_request("Workspace name is required"));
    }

    let visibility = payload.visibility.as_deref().unwrap_or("private");
    if !matches!(visibility, "private" | "shared") {
        return Err(AppError::bad_request("Workspace visibility must be private or shared"));
    }

    super::repo::create_workspace(&state.db, actor_user_id, payload).await
}

pub async fn get_workspace(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceWithMembersResponse> {
    super::repo::get_workspace(&state.db, actor_user_id, workspace_id).await
}

pub async fn update_workspace(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    payload: UpdateWorkspaceRequest,
) -> AppResult<WorkspaceResponse> {
    if let Some(name) = &payload.name {
        if name.trim().is_empty() {
            return Err(AppError::bad_request("Workspace name cannot be empty"));
        }
    }

    if let Some(visibility) = &payload.visibility {
        if !matches!(visibility.as_str(), "private" | "shared") {
            return Err(AppError::bad_request("Workspace visibility must be private or shared"));
        }
    }

    super::repo::update_workspace(&state.db, actor_user_id, workspace_id, payload).await
}

pub async fn delete_workspace(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceResponse> {
    super::repo::delete_workspace(&state.db, actor_user_id, workspace_id).await
}

pub async fn list_members(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceMembersListResponse> {
    super::repo::list_members(&state.db, actor_user_id, workspace_id).await
}

pub async fn add_member(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    payload: AddWorkspaceMemberRequest,
) -> AppResult<WorkspaceMemberResponse> {
    let role = payload.role.as_str();
    if !matches!(role, "admin" | "member") {
        return Err(AppError::bad_request("Workspace member role must be admin or member"));
    }

    super::repo::add_member(&state.db, actor_user_id, workspace_id, payload).await
}

pub async fn update_member(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    member_id: Uuid,
    payload: UpdateWorkspaceMemberRequest,
) -> AppResult<WorkspaceMemberResponse> {
    if let Some(role) = &payload.role {
        if !matches!(role.as_str(), "admin" | "member") {
            return Err(AppError::bad_request("Workspace member role must be admin or member"));
        }
    }

    super::repo::update_member(&state.db, actor_user_id, workspace_id, member_id, payload).await
}

pub async fn remove_member(
    state: &AppState,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    member_id: Uuid,
) -> AppResult<WorkspaceMemberResponse> {
    super::repo::remove_member(&state.db, actor_user_id, workspace_id, member_id).await
}
