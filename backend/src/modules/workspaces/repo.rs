use serde_json::json;
use sqlx::{PgPool, Row};
use uuid::Uuid;

use crate::{
    error::{AppError, AppResult},
    modules::{
        audit::repo::{record_audit, NewAuditLogEntry},
        common::{
            ensure_user_exists, normalize_limit, require_workspace_access, require_workspace_admin,
            require_workspace_owner, trim_to_option,
        },
    },
};

use super::dto::{
    AddWorkspaceMemberRequest, CreateWorkspaceRequest, ListWorkspacesQuery, PageInfo,
    UpdateWorkspaceMemberRequest, UpdateWorkspaceRequest, WorkspaceListResponse,
    WorkspaceMemberResponse, WorkspaceMembersListResponse, WorkspaceResponse,
    WorkspaceWithMembersResponse,
};

fn pg_err(err: sqlx::Error, conflict_message: &'static str) -> AppError {
    match err {
        sqlx::Error::Database(db_err) if db_err.code().as_deref() == Some("23505") => {
            AppError::conflict(conflict_message)
        }
        other => other.into(),
    }
}

fn map_workspace(row: &sqlx::postgres::PgRow) -> AppResult<WorkspaceResponse> {
    Ok(WorkspaceResponse {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        name: row.try_get("name")?,
        slug: row.try_get("slug")?,
        description: row.try_get("description")?,
        visibility: row.try_get("visibility")?,
        owner_user_id: row.try_get::<Uuid, _>("owner_user_id")?.to_string(),
        member_count: row.try_get::<i64, _>("member_count")?,
        is_archived: row.try_get::<Option<String>, _>("archived_at")?.is_some(),
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
        archived_at: row.try_get("archived_at")?,
    })
}

fn map_workspace_member(row: &sqlx::postgres::PgRow) -> AppResult<WorkspaceMemberResponse> {
    Ok(WorkspaceMemberResponse {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        workspace_id: row.try_get::<Uuid, _>("workspace_id")?.to_string(),
        user_id: row.try_get::<Uuid, _>("user_id")?.to_string(),
        role: row.try_get("role")?,
        status: if row.try_get::<Option<String>, _>("removed_at")?.is_some() {
            "removed".to_string()
        } else {
            "active".to_string()
        },
        invited_by_user_id: row
            .try_get::<Option<Uuid>, _>("invited_by_user_id")?
            .map(|id| id.to_string()),
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
        removed_at: row.try_get("removed_at")?,
    })
}

async fn fetch_workspace(pool: &PgPool, workspace_id: Uuid) -> AppResult<WorkspaceResponse> {
    let row = sqlx::query(
        r#"
        select
          w.id,
          w.name,
          w.slug,
          w.description,
          w.visibility,
          w.owner_user_id,
          to_char(w.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(w.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          case when w.archived_at is null then null else to_char(w.archived_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end as archived_at,
          (
            select count(*)::bigint
            from workspace_members wm
            where wm.workspace_id = w.id
              and wm.deactivated_at is null
              and wm.deleted_at is null
          ) as member_count
        from workspaces w
        where w.id = $1
          and w.deleted_at is null
        "#,
    )
    .bind(workspace_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Workspace not found"))?;

    map_workspace(&row)
}

pub async fn list_workspaces(
    pool: &PgPool,
    actor_user_id: Uuid,
    query: ListWorkspacesQuery,
) -> AppResult<WorkspaceListResponse> {
    ensure_user_exists(pool, actor_user_id).await?;

    let limit = normalize_limit(query.limit);
    let search = trim_to_option(query.q);
    let archived = query.archived.unwrap_or(false);
    let _cursor = query.cursor;

    let rows = sqlx::query(
        r#"
        select
          w.id,
          w.name,
          w.slug,
          w.description,
          w.visibility,
          w.owner_user_id,
          to_char(w.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(w.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          case when w.archived_at is null then null else to_char(w.archived_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end as archived_at,
          (
            select count(*)::bigint
            from workspace_members wm2
            where wm2.workspace_id = w.id
              and wm2.deactivated_at is null
              and wm2.deleted_at is null
          ) as member_count
        from workspaces w
        where w.deleted_at is null
          and (($2 = true and w.archived_at is not null) or ($2 = false and w.archived_at is null))
          and (
            w.owner_user_id = $1
            or exists (
              select 1
              from workspace_members wm
              where wm.workspace_id = w.id
                and wm.user_id = $1
                and wm.deactivated_at is null
                and wm.deleted_at is null
            )
          )
          and (
            $3::text is null
            or w.name ilike '%' || $3 || '%'
            or coalesce(w.slug, '') ilike '%' || $3 || '%'
            or coalesce(w.description, '') ilike '%' || $3 || '%'
          )
        order by w.updated_at desc, w.id desc
        limit $4
        "#,
    )
    .bind(actor_user_id)
    .bind(archived)
    .bind(search)
    .bind(limit)
    .fetch_all(pool)
    .await?;

    let items = rows
        .iter()
        .map(map_workspace)
        .collect::<AppResult<Vec<_>>>()?;

    Ok(WorkspaceListResponse {
        items,
        page_info: PageInfo {
            has_next_page: false,
            next_cursor: None,
        },
    })
}

pub async fn create_workspace(
    pool: &PgPool,
    actor_user_id: Uuid,
    payload: CreateWorkspaceRequest,
) -> AppResult<WorkspaceResponse> {
    ensure_user_exists(pool, actor_user_id).await?;

    let workspace_id = Uuid::now_v7();
    let member_id = Uuid::now_v7();
    let name = payload.name.trim().to_string();
    let slug = trim_to_option(payload.slug);
    let description = trim_to_option(payload.description);
    let visibility = payload.visibility.unwrap_or_else(|| "private".to_string());

    let mut tx = pool.begin().await?;

    let res = sqlx::query(
        r#"
        insert into workspaces (id, name, slug, description, owner_user_id, visibility)
        values ($1, $2, $3, $4, $5, $6)
        "#,
    )
    .bind(workspace_id)
    .bind(name)
    .bind(slug)
    .bind(description)
    .bind(actor_user_id)
    .bind(visibility)
    .execute(&mut *tx)
    .await;

    if let Err(err) = res {
        return Err(pg_err(err, "Workspace slug already exists"));
    }

    sqlx::query(
        r#"
        insert into workspace_members (id, workspace_id, user_id, role, invited_by_user_id)
        values ($1, $2, $3, 'owner', $3)
        "#,
    )
    .bind(member_id)
    .bind(workspace_id)
    .bind(actor_user_id)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    let workspace = fetch_workspace(pool, workspace_id).await?;
    let _audit_id = record_audit(
        pool,
        &NewAuditLogEntry {
            workspace_id: Some(workspace_id),
            actor_user_id: Some(actor_user_id),
            actor_device_id: None,
            actor_replica_id: None,
            action_type: "workspace.created".to_string(),
            target_entity_type: Some("workspace".to_string()),
            target_entity_id: Some(workspace_id),
            request_id: None,
            metadata_jsonb: json!({
                "name": workspace.name.clone(),
                "visibility": workspace.visibility.clone(),
            }),
        },
    )
    .await?;

    Ok(workspace)
}

pub async fn get_workspace(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceWithMembersResponse> {
    let current_user_role = require_workspace_access(pool, workspace_id, actor_user_id).await?;
    let workspace = fetch_workspace(pool, workspace_id).await?;
    let members = fetch_members(pool, workspace_id).await?;

    Ok(WorkspaceWithMembersResponse {
        workspace,
        current_user_role,
        members,
    })
}

pub async fn update_workspace(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    payload: UpdateWorkspaceRequest,
) -> AppResult<WorkspaceResponse> {
    require_workspace_admin(pool, workspace_id, actor_user_id).await?;

    let name = payload.name.map(|value| value.trim().to_string());
    let slug_changed = payload.slug.is_some();
    let description_changed = payload.description.is_some();
    let slug = payload.slug.map(trim_to_option);
    let description = payload.description.map(trim_to_option);

    let res = sqlx::query(
        r#"
        update workspaces
        set
          name = coalesce($2, name),
          slug = case when $3 then $4 else slug end,
          description = case when $5 then $6 else description end,
          visibility = coalesce($7, visibility)
        where id = $1
          and deleted_at is null
        "#,
    )
    .bind(workspace_id)
    .bind(name)
    .bind(slug_changed)
    .bind(slug.flatten())
    .bind(description_changed)
    .bind(description.flatten())
    .bind(payload.visibility)
    .execute(pool)
    .await;

    match res {
        Ok(done) if done.rows_affected() == 0 => Err(AppError::not_found("Workspace not found")),
        Ok(_) => {
            let workspace = fetch_workspace(pool, workspace_id).await?;
            let _audit_id = record_audit(
                pool,
                &NewAuditLogEntry {
                    workspace_id: Some(workspace_id),
                    actor_user_id: Some(actor_user_id),
                    actor_device_id: None,
                    actor_replica_id: None,
                    action_type: "workspace.updated".to_string(),
                    target_entity_type: Some("workspace".to_string()),
                    target_entity_id: Some(workspace_id),
                    request_id: None,
                    metadata_jsonb: json!({
                        "name": workspace.name.clone(),
                        "slug": workspace.slug.clone(),
                        "visibility": workspace.visibility.clone(),
                    }),
                },
            )
            .await?;
            Ok(workspace)
        }
        Err(err) => Err(pg_err(err, "Workspace slug already exists")),
    }
}

pub async fn delete_workspace(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceResponse> {
    require_workspace_owner(pool, workspace_id, actor_user_id).await?;
    let workspace = fetch_workspace(pool, workspace_id).await?;

    let res = sqlx::query(
        r#"
        update workspaces
        set deleted_at = now(), updated_at = now()
        where id = $1
          and deleted_at is null
        "#,
    )
    .bind(workspace_id)
    .execute(pool)
    .await?;

    if res.rows_affected() == 0 {
        return Err(AppError::not_found("Workspace not found"));
    }

    sqlx::query(
        r#"
        update workspace_members
        set deactivated_at = coalesce(deactivated_at, now()),
            deleted_at = coalesce(deleted_at, now())
        where workspace_id = $1
          and deleted_at is null
        "#,
    )
    .bind(workspace_id)
    .execute(pool)
    .await?;

    let _audit_id = record_audit(
        pool,
        &NewAuditLogEntry {
            workspace_id: Some(workspace_id),
            actor_user_id: Some(actor_user_id),
            actor_device_id: None,
            actor_replica_id: None,
            action_type: "workspace.deleted".to_string(),
            target_entity_type: Some("workspace".to_string()),
            target_entity_id: Some(workspace_id),
            request_id: None,
            metadata_jsonb: json!({
                "name": workspace.name.clone(),
                "visibility": workspace.visibility.clone(),
            }),
        },
    )
    .await?;

    Ok(workspace)
}

async fn fetch_members(pool: &PgPool, workspace_id: Uuid) -> AppResult<Vec<WorkspaceMemberResponse>> {
    let rows = sqlx::query(
        r#"
        select
          wm.id,
          wm.workspace_id,
          wm.user_id,
          wm.role,
          wm.invited_by_user_id,
          to_char(wm.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(wm.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          case when wm.deactivated_at is null then null else to_char(wm.deactivated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end as removed_at
        from workspace_members wm
        where wm.workspace_id = $1
          and wm.deleted_at is null
        order by wm.created_at asc, wm.id asc
        "#,
    )
    .bind(workspace_id)
    .fetch_all(pool)
    .await?;

    rows.iter().map(map_workspace_member).collect()
}

pub async fn list_members(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
) -> AppResult<WorkspaceMembersListResponse> {
    require_workspace_access(pool, workspace_id, actor_user_id).await?;
    let items = fetch_members(pool, workspace_id).await?;
    Ok(WorkspaceMembersListResponse {
        items,
        page_info: PageInfo {
            has_next_page: false,
            next_cursor: None,
        },
    })
}

pub async fn add_member(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    payload: AddWorkspaceMemberRequest,
) -> AppResult<WorkspaceMemberResponse> {
    require_workspace_admin(pool, workspace_id, actor_user_id).await?;

    let user_id = Uuid::parse_str(&payload.user_id)
        .map_err(|_| AppError::bad_request("userId must be a valid UUID"))?;
    ensure_user_exists(pool, user_id).await?;

    let row = sqlx::query(
        r#"
        insert into workspace_members (id, workspace_id, user_id, role, invited_by_user_id)
        values ($1, $2, $3, $4, $5)
        on conflict (workspace_id, user_id)
        where deactivated_at is null and deleted_at is null
        do nothing
        returning
          id,
          workspace_id,
          user_id,
          role,
          invited_by_user_id,
          to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          null::text as removed_at
        "#,
    )
    .bind(Uuid::now_v7())
    .bind(workspace_id)
    .bind(user_id)
    .bind(payload.role)
    .bind(actor_user_id)
    .fetch_optional(pool)
    .await?;

    let row = match row {
        Some(row) => row,
        None => {
            return Err(AppError::conflict(
                "Workspace member already exists or is still active",
            ))
        }
    };

    let member = map_workspace_member(&row)?;
    let _audit_id = record_audit(
        pool,
        &NewAuditLogEntry {
            workspace_id: Some(workspace_id),
            actor_user_id: Some(actor_user_id),
            actor_device_id: None,
            actor_replica_id: None,
            action_type: "workspace.member_added".to_string(),
            target_entity_type: Some("workspace_member".to_string()),
            target_entity_id: Some(Uuid::parse_str(&member.id).expect("valid member id")),
            request_id: None,
            metadata_jsonb: json!({
                "memberUserId": member.user_id.clone(),
                "role": member.role.clone(),
            }),
        },
    )
    .await?;

    Ok(member)
}

pub async fn update_member(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    member_id: Uuid,
    payload: UpdateWorkspaceMemberRequest,
) -> AppResult<WorkspaceMemberResponse> {
    require_workspace_admin(pool, workspace_id, actor_user_id).await?;

    let Some(role) = payload.role else {
        let items = fetch_members(pool, workspace_id).await?;
        return items
            .into_iter()
            .find(|item| item.id == member_id.to_string())
            .ok_or_else(|| AppError::not_found("Workspace member not found"));
    };

    let row = sqlx::query(
        r#"
        update workspace_members
        set role = $3
        where id = $1
          and workspace_id = $2
          and deleted_at is null
          and role <> 'owner'
        returning
          id,
          workspace_id,
          user_id,
          role,
          invited_by_user_id,
          to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          case when deactivated_at is null then null else to_char(deactivated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end as removed_at
        "#,
    )
    .bind(member_id)
    .bind(workspace_id)
    .bind(role)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Workspace member not found"))?;

    let member = map_workspace_member(&row)?;
    let _audit_id = record_audit(
        pool,
        &NewAuditLogEntry {
            workspace_id: Some(workspace_id),
            actor_user_id: Some(actor_user_id),
            actor_device_id: None,
            actor_replica_id: None,
            action_type: "workspace.member_updated".to_string(),
            target_entity_type: Some("workspace_member".to_string()),
            target_entity_id: Some(Uuid::parse_str(&member.id).expect("valid member id")),
            request_id: None,
            metadata_jsonb: json!({
                "memberUserId": member.user_id.clone(),
                "role": member.role.clone(),
                "status": member.status.clone(),
            }),
        },
    )
    .await?;

    Ok(member)
}

pub async fn remove_member(
    pool: &PgPool,
    actor_user_id: Uuid,
    workspace_id: Uuid,
    member_id: Uuid,
) -> AppResult<WorkspaceMemberResponse> {
    require_workspace_admin(pool, workspace_id, actor_user_id).await?;

    let row = sqlx::query(
        r#"
        update workspace_members
        set deactivated_at = coalesce(deactivated_at, now())
        where id = $1
          and workspace_id = $2
          and deleted_at is null
          and role <> 'owner'
          and role <> 'owner'
        returning
          id,
          workspace_id,
          user_id,
          role,
          invited_by_user_id,
          to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as created_at,
          to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as updated_at,
          case when deactivated_at is null then null else to_char(deactivated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end as removed_at
        "#,
    )
    .bind(member_id)
    .bind(workspace_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| AppError::not_found("Workspace member not found or cannot remove owner"))?;

    let member = map_workspace_member(&row)?;
    let _audit_id = record_audit(
        pool,
        &NewAuditLogEntry {
            workspace_id: Some(workspace_id),
            actor_user_id: Some(actor_user_id),
            actor_device_id: None,
            actor_replica_id: None,
            action_type: "workspace.member_removed".to_string(),
            target_entity_type: Some("workspace_member".to_string()),
            target_entity_id: Some(Uuid::parse_str(&member.id).expect("valid member id")),
            request_id: None,
            metadata_jsonb: json!({
                "memberUserId": member.user_id.clone(),
                "role": member.role.clone(),
                "status": member.status.clone(),
            }),
        },
    )
    .await?;

    Ok(member)
}
