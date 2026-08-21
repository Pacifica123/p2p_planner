use std::{collections::HashSet, sync::Arc, time::Duration};

use p2p_kanban_nostr_transport::{
    NostrTransport, NostrTransportConfig, RecoveredRoamingEvent, RoamingBoardEvent,
    ROAMING_PROTOCOL_VERSION,
};
use serde_json::{json, Value};
use sqlx::{PgPool, Postgres, Row, Transaction};
use uuid::Uuid;

use crate::config::Settings;

const CARD_FIELDS: &[&str] = &[
    "columnId",
    "parentCardId",
    "title",
    "description",
    "priority",
    "position",
    "startAt",
    "dueAt",
    "isArchived",
    "checklists",
];

const CHECKLIST_DELTA_KEY: &str = "checklistDelta";

fn find_checklist<'a>(checklists: &'a Value, checklist_id: Uuid) -> Option<&'a Value> {
    let expected = checklist_id.to_string();
    checklists
        .as_array()?
        .iter()
        .find(|checklist| string_field(checklist, "id") == Some(expected.as_str()))
}

fn find_checklist_item<'a>(checklists: &'a Value, item_id: Uuid) -> Option<(&'a Value, &'a Value)> {
    let expected = item_id.to_string();
    checklists.as_array()?.iter().find_map(|checklist| {
        checklist
            .get("items")?
            .as_array()?
            .iter()
            .find(|item| string_field(item, "id") == Some(expected.as_str()))
            .map(|item| (checklist, item))
    })
}

fn checklist_delta_from_activity(
    kind: &str,
    entity_type: &str,
    entity_id: Uuid,
    card_id: Uuid,
    field_mask: &[String],
    checklists: &Value,
    occurred_at: &str,
) -> Option<Value> {
    let fields = if kind.ends_with(".created") {
        vec!["*".to_string()]
    } else if kind.ends_with(".deleted") {
        vec!["__lifecycle".to_string()]
    } else {
        field_mask.to_vec()
    };

    match entity_type {
        "checklist" if kind.ends_with(".deleted") => Some(json!({
            "kind": "checklist.delete",
            "cardId": card_id,
            "checklistId": entity_id,
            "fieldMask": fields,
            "deletedAt": occurred_at,
        })),
        "checklist" => find_checklist(checklists, entity_id).map_or_else(
            || {
                Some(json!({
                    "kind": "checklist.delete",
                    "cardId": card_id,
                    "checklistId": entity_id,
                    "fieldMask": ["__lifecycle"],
                    "deletedAt": occurred_at,
                }))
            },
            |checklist| {
                Some(json!({
                    "kind": "checklist.put",
                    "cardId": card_id,
                    "checklistId": entity_id,
                    "fieldMask": fields,
                    "checklist": checklist,
                }))
            },
        ),
        "checklist_item" if kind.ends_with(".deleted") => Some(json!({
            "kind": "checklist_item.delete",
            "cardId": card_id,
            "itemId": entity_id,
            "fieldMask": fields,
            "deletedAt": occurred_at,
        })),
        "checklist_item" => find_checklist_item(checklists, entity_id).map_or_else(
            || {
                Some(json!({
                    "kind": "checklist_item.delete",
                    "cardId": card_id,
                    "itemId": entity_id,
                    "fieldMask": ["__lifecycle"],
                    "deletedAt": occurred_at,
                }))
            },
            |(checklist, item)| {
                Some(json!({
                    "kind": "checklist_item.put",
                    "cardId": card_id,
                    "checklistId": string_field(checklist, "id"),
                    "itemId": entity_id,
                    "fieldMask": fields,
                    "item": item,
                }))
            },
        ),
        _ => None,
    }
}

pub async fn run(settings: std::sync::Arc<Settings>, db: PgPool) -> anyhow::Result<()> {
    if !settings.transports.nostr.enabled {
        return Ok(());
    }
    let nostr = &settings.transports.nostr;
    let transport = NostrTransport::connect(NostrTransportConfig {
        relays: nostr.relays.clone(),
        secret_key: nostr.secret_key.clone().unwrap_or_default(),
        master_key: nostr.master_key()?,
        event_kind: nostr.event_kind,
        fetch_timeout: Duration::from_secs(nostr.fetch_timeout_secs),
        min_relay_acks: nostr.min_relay_acks,
    })
    .await?;

    enqueue_backfill(&db).await?;
    let poll = Duration::from_millis(settings.transports.worker_poll_interval_ms.max(1_000));
    loop {
        tokio::join!(
            publish_pending(&db, &transport, settings.transports.batch_size),
            publish_pending_board_settings(&db, &transport, settings.transports.batch_size),
            ingest_remote(&db, &transport),
        );
        tokio::time::sleep(poll).await;
    }
}

async fn enqueue_backfill(pool: &PgPool) -> anyhow::Result<()> {
    sqlx::query(
        r#"
        insert into roaming_board_outbox (
          id, source_key, workspace_id, board_id, card_id
        )
        select
          gen_random_uuid(),
          'backfill:' || c.id::text || ':' || extract(epoch from c.updated_at)::bigint::text,
          b.workspace_id,
          c.board_id,
          c.id
        from cards c
        join boards b on b.id = c.board_id
        join workspaces w on w.id = b.workspace_id
        where c.deleted_at is null
          and b.deleted_at is null
          and w.deleted_at is null
        on conflict (source_key) do nothing
        "#,
    )
    .execute(pool)
    .await?;
    Ok(())
}

async fn publish_pending(pool: &PgPool, transport: &NostrTransport, limit: i64) {
    let rows = match sqlx::query(
        r#"
        select
          o.id,
          o.event_seq,
          o.workspace_id,
          o.board_id,
          o.card_id,
          ae.kind as source_activity_kind,
          ae.entity_type as source_entity_type,
          ae.entity_id as source_entity_id,
          ae.field_mask as source_field_mask,
          n.replica_id as node_replica_id,
          rbc.board_key_base64,
          case
            when c.deleted_at is not null or t.entity_id is not null then 'card.delete'
            else 'card.put'
          end as roaming_operation,
          case when coalesce(c.deleted_at, t.deleted_at) is null then null else
            to_char(coalesce(c.deleted_at, t.deleted_at) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
          end as deleted_at,
          to_char(o.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as occurred_at,
          (
            floor(extract(epoch from o.created_at) * 1000)::bigint * 1000
            + (o.event_seq % 1000)
          ) as logical_clock,
          jsonb_build_object(
            'id', c.id::text,
            'boardId', c.board_id::text,
            'columnId', c.column_id::text,
            'parentCardId', c.parent_card_id::text,
            'title', c.title,
            'description', c.description,
            'priority', c.priority,
            'position', c.position::double precision,
            'startAt', case when c.start_at is null then null else to_char(c.start_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
            'dueAt', case when c.due_at is null then null else to_char(c.due_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
            'isArchived', c.archived_at is not null,
            'labelIds', '[]'::jsonb,
            'checklistCount', (
              select count(*)::bigint
              from checklists ch
              where ch.card_id = c.id and ch.deleted_at is null
            ),
            'checklistItemCount', (
              select count(*)::bigint
              from checklist_items chi
              join checklists ch on ch.id = chi.checklist_id
              where ch.card_id = c.id and ch.deleted_at is null and chi.deleted_at is null
            ),
            'checklistCompletedItemCount', (
              select count(*)::bigint
              from checklist_items chi
              join checklists ch on ch.id = chi.checklist_id
              where ch.card_id = c.id
                and ch.deleted_at is null
                and chi.deleted_at is null
                and chi.is_done = true
            ),
            'commentCount', 0,
            'createdByUserId', c.created_by_user_id::text,
            'createdAt', to_char(c.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
            'updatedAt', to_char(c.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
            'archivedAt', case when c.archived_at is null then null else to_char(c.archived_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end
          ) as card,
          coalesce((
            select jsonb_agg(
              jsonb_build_object(
                'id', ch.id::text,
                'cardId', ch.card_id::text,
                'title', ch.title,
                'position', ch.position::double precision,
                'items', coalesce((
                  select jsonb_agg(
                    jsonb_build_object(
                      'id', chi.id::text,
                      'checklistId', chi.checklist_id::text,
                      'title', chi.title,
                      'isDone', chi.is_done,
                      'position', chi.position::double precision,
                      'completedAt', case when chi.completed_at is null then null else to_char(chi.completed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
                      'createdAt', to_char(chi.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                      'updatedAt', to_char(chi.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
                    )
                    order by chi.position, chi.id
                  )
                  from checklist_items chi
                  where chi.checklist_id = ch.id and chi.deleted_at is null
                ), '[]'::jsonb),
                'createdAt', to_char(ch.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                'updatedAt', to_char(ch.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
              )
              order by ch.position, ch.id
            )
            from checklists ch
            where ch.card_id = c.id and ch.deleted_at is null
          ), '[]'::jsonb) as checklists
        from roaming_board_outbox o
        join cards c on c.id = o.card_id
        left join activity_entries ae on ae.id = o.source_activity_id
        cross join local_node_identity n
        left join roaming_board_capabilities rbc on rbc.board_id = o.board_id
        left join tombstones t
          on t.entity_type = 'card'
         and t.entity_id = o.card_id
        where o.status in ('pending', 'retry')
          and o.next_attempt_at <= now()
        order by o.event_seq
        limit $1
        "#,
    )
    .bind(limit.clamp(1, 500))
    .fetch_all(pool)
    .await
    {
        Ok(rows) => rows,
        Err(error) => {
            tracing::warn!(%error, "could not load roaming outbox");
            return;
        }
    };

    for row in rows {
        let outbox_id: Uuid = match row.try_get("id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let operation: String = row
            .try_get("roaming_operation")
            .unwrap_or_else(|_| "card.put".to_string());
        let deleted_at = row
            .try_get::<Option<String>, _>("deleted_at")
            .ok()
            .flatten();
        let card = row
            .try_get::<Value, _>("card")
            .unwrap_or_else(|_| json!({}));
        let checklists = row
            .try_get::<Value, _>("checklists")
            .unwrap_or_else(|_| json!([]));
        let source_kind = row
            .try_get::<Option<String>, _>("source_activity_kind")
            .ok()
            .flatten();
        let source_entity_type = row
            .try_get::<Option<String>, _>("source_entity_type")
            .ok()
            .flatten();
        let source_entity_id = row
            .try_get::<Option<Uuid>, _>("source_entity_id")
            .ok()
            .flatten();
        let source_field_mask = row
            .try_get::<Option<Vec<String>>, _>("source_field_mask")
            .ok()
            .flatten()
            .unwrap_or_default();
        let occurred_at: String = row.try_get("occurred_at").unwrap_or_default();
        let card_id: Uuid = row.try_get("card_id").unwrap();
        let checklist_delta = source_kind
            .as_deref()
            .zip(source_entity_type.as_deref())
            .zip(source_entity_id)
            .and_then(|((kind, entity_type), entity_id)| {
                checklist_delta_from_activity(
                    kind,
                    entity_type,
                    entity_id,
                    card_id,
                    &source_field_mask,
                    &checklists,
                    &occurred_at,
                )
            });
        let field_mask = if operation == "card.delete" {
            vec!["__lifecycle".to_string()]
        } else if checklist_delta.is_some() {
            vec!["checklists".to_string()]
        } else if source_kind.as_deref() == Some("card.created") || source_kind.is_none() {
            vec!["*".to_string()]
        } else {
            source_field_mask
        };
        let payload = if operation == "card.delete" {
            json!({ "deletedAt": deleted_at })
        } else if let Some(delta) = checklist_delta {
            json!({
                "card": card,
                "checklistDelta": delta,
            })
        } else if field_mask.iter().any(|field| field == "*") {
            json!({
                "card": card,
                "checklists": checklists,
            })
        } else {
            json!({ "card": card })
        };
        let event = RoamingBoardEvent {
            protocol_version: ROAMING_PROTOCOL_VERSION.to_string(),
            event_id: outbox_id.to_string(),
            workspace_id: row.try_get::<Uuid, _>("workspace_id").unwrap().to_string(),
            board_id: row.try_get::<Uuid, _>("board_id").unwrap().to_string(),
            replica_id: row
                .try_get::<Uuid, _>("node_replica_id")
                .unwrap()
                .to_string(),
            replica_seq: row.try_get("event_seq").unwrap_or(1),
            logical_clock: row.try_get("logical_clock").unwrap_or(1),
            entity_type: "card".to_string(),
            entity_id: card_id.to_string(),
            operation: operation.clone(),
            field_mask,
            payload,
            occurred_at,
        };
        let imported_board_key = row
            .try_get::<Option<String>, _>("board_key_base64")
            .ok()
            .flatten();
        let delivery = match imported_board_key.as_deref() {
            Some(board_key) => {
                transport
                    .publish_roaming_with_board_key(&event, board_key)
                    .await
            }
            None => transport.publish_roaming(&event).await,
        };
        match delivery {
            Ok(receipt) => {
                let _ = sqlx::query(
                    "update roaming_board_outbox set status = 'delivered', delivered_at = now(), nostr_event_id = $2, last_error = null where id = $1",
                )
                .bind(outbox_id)
                .bind(receipt.nostr_event_id)
                .execute(pool)
                .await;
            }
            Err(error) => {
                let _ = sqlx::query(
                    r#"
                    update roaming_board_outbox
                    set
                      status = case when attempt_count + 1 >= 12 then 'dead_letter' else 'retry' end,
                      attempt_count = attempt_count + 1,
                      next_attempt_at = now() + make_interval(secs => least(300, (attempt_count + 1) * 5)),
                      last_error = left($2, 1000)
                    where id = $1
                    "#,
                )
                .bind(outbox_id)
                .bind(format!("{error:#}"))
                .execute(pool)
                .await;
            }
        }
    }
}

async fn publish_pending_board_settings(pool: &PgPool, transport: &NostrTransport, limit: i64) {
    let rows = match sqlx::query(
        r#"
        select
          o.id,
          o.event_seq,
          o.workspace_id,
          o.board_id,
          n.replica_id as node_replica_id,
          rbc.board_key_base64,
          to_char(o.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') as occurred_at,
          (
            floor(extract(epoch from o.created_at) * 1000)::bigint * 1000
            + (o.event_seq % 1000)
          ) as logical_clock,
          jsonb_build_object(
            'boardId', b.id::text,
            'isCustomized', a.board_id is not null,
            'themePreset', coalesce(a.theme_preset, 'system'),
            'wallpaper', jsonb_build_object(
              'kind', coalesce(a.wallpaper_kind, 'none'),
              'value', a.wallpaper_value
            ),
            'columnDensity', coalesce(a.column_density, 'comfortable'),
            'cardPreviewMode', coalesce(a.card_preview_mode, 'expanded'),
            'showCardDescription', coalesce(a.show_card_description, true),
            'showCardDates', coalesce(a.show_card_dates, true),
            'showChecklistProgress', coalesce(a.show_checklist_progress, true),
            'customProperties', coalesce(a.custom_properties_jsonb, '{}'::jsonb),
            'createdAt', case when a.created_at is null then null else to_char(a.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
            'updatedAt', case when a.updated_at is null then null else to_char(a.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end
          ) as appearance
        from roaming_board_settings_outbox o
        join boards b on b.id = o.board_id and b.deleted_at is null
        left join board_appearance_settings a on a.board_id = o.board_id
        cross join local_node_identity n
        left join roaming_board_capabilities rbc on rbc.board_id = o.board_id
        where o.status in ('pending', 'retry')
          and o.next_attempt_at <= now()
        order by o.event_seq
        limit $1
        "#,
    )
    .bind(limit.clamp(1, 500))
    .fetch_all(pool)
    .await
    {
        Ok(rows) => rows,
        Err(error) => {
            tracing::warn!(%error, "could not load roaming board settings outbox");
            return;
        }
    };

    for row in rows {
        let outbox_id: Uuid = match row.try_get("id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let board_id: Uuid = match row.try_get("board_id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let logical_clock = row.try_get::<i64, _>("logical_clock").unwrap_or(1);
        let event = RoamingBoardEvent {
            protocol_version: ROAMING_PROTOCOL_VERSION.to_string(),
            event_id: outbox_id.to_string(),
            workspace_id: row
                .try_get::<Uuid, _>("workspace_id")
                .unwrap_or_default()
                .to_string(),
            board_id: board_id.to_string(),
            replica_id: row
                .try_get::<Uuid, _>("node_replica_id")
                .unwrap_or_default()
                .to_string(),
            replica_seq: logical_clock,
            logical_clock,
            entity_type: "board".to_string(),
            entity_id: board_id.to_string(),
            operation: "board.appearance.put".to_string(),
            field_mask: vec!["appearance".to_string()],
            payload: json!({
                "appearance": row
                    .try_get::<Value, _>("appearance")
                    .unwrap_or_else(|_| json!({})),
            }),
            occurred_at: row
                .try_get("occurred_at")
                .unwrap_or_else(|_| chrono_fallback_timestamp()),
        };
        let imported_board_key = row
            .try_get::<Option<String>, _>("board_key_base64")
            .ok()
            .flatten();
        let delivery = match imported_board_key.as_deref() {
            Some(board_key) => {
                transport
                    .publish_roaming_with_board_key(&event, board_key)
                    .await
            }
            None => transport.publish_roaming(&event).await,
        };
        match delivery {
            Ok(receipt) => {
                let _ = sqlx::query(
                    "update roaming_board_settings_outbox set status = 'delivered', delivered_at = now(), nostr_event_id = $2, last_error = null where id = $1",
                )
                .bind(outbox_id)
                .bind(receipt.nostr_event_id)
                .execute(pool)
                .await;
            }
            Err(error) => {
                let _ = sqlx::query(
                    r#"
                    update roaming_board_settings_outbox
                    set
                      status = case when attempt_count + 1 >= 12 then 'dead_letter' else 'retry' end,
                      attempt_count = attempt_count + 1,
                      next_attempt_at = now() + make_interval(secs => least(300, (attempt_count + 1) * 5)),
                      last_error = left($2, 1000)
                    where id = $1
                    "#,
                )
                .bind(outbox_id)
                .bind(format!("{error:#}"))
                .execute(pool)
                .await;
            }
        }
    }
}

fn chrono_fallback_timestamp() -> String {
    "1970-01-01T00:00:00.000Z".to_string()
}

async fn ingest_remote(pool: &PgPool, transport: &NostrTransport) {
    let boards = match sqlx::query(
        r#"
        select b.id as board_id, b.workspace_id, rbc.board_key_base64
        from boards b
        join workspaces w on w.id = b.workspace_id
        left join roaming_board_capabilities rbc on rbc.board_id = b.id
        where b.deleted_at is null and w.deleted_at is null
        order by b.id
        "#,
    )
    .fetch_all(pool)
    .await
    {
        Ok(values) => values,
        Err(error) => {
            tracing::warn!(%error, "could not list roaming boards");
            return;
        }
    };

    let concurrency = Arc::new(tokio::sync::Semaphore::new(6));
    let mut fetches = tokio::task::JoinSet::new();
    for board in boards {
        let board_id: Uuid = match board.try_get("board_id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let workspace_id: Uuid = match board.try_get("workspace_id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let imported_board_key = board
            .try_get::<Option<String>, _>("board_key_base64")
            .ok()
            .flatten();
        let transport = transport.clone();
        let concurrency = Arc::clone(&concurrency);
        fetches.spawn(async move {
            let _permit = concurrency.acquire_owned().await.ok();
            let recovered = match imported_board_key.as_deref() {
                Some(board_key) => {
                    transport
                        .recover_roaming_with_board_key(&board_id.to_string(), board_key)
                        .await
                }
                None => transport.recover_roaming(&board_id.to_string()).await,
            };
            (board_id, workspace_id, recovered)
        });
    }

    while let Some(result) = fetches.join_next().await {
        let Ok((board_id, workspace_id, recovered)) = result else {
            continue;
        };
        let events = match recovered {
            Ok(events) => events,
            Err(error) => {
                tracing::debug!(%board_id, %error, "could not pull roaming events");
                continue;
            }
        };
        for recovered in events {
            if let Err(error) = apply_remote_event(pool, workspace_id, &recovered).await {
                tracing::warn!(
                    event_id = %recovered.event.event_id,
                    %error,
                    "rejected roaming event"
                );
            }
        }
    }
}

fn string_field<'a>(card: &'a Value, field: &str) -> Option<&'a str> {
    card.get(field).and_then(Value::as_str)
}

fn finite_number(value: &Value, field: &str, fallback: f64) -> anyhow::Result<f64> {
    let number = value.get(field).and_then(Value::as_f64).unwrap_or(fallback);
    if !number.is_finite() {
        anyhow::bail!("{field} must be finite");
    }
    Ok(number)
}

fn normalized_card_priority(card: &Value) -> anyhow::Result<Option<&str>> {
    let priority = string_field(card, "priority");
    if priority.is_some_and(|value| !matches!(value, "low" | "medium" | "high" | "urgent")) {
        anyhow::bail!("unsupported card priority");
    }
    Ok(priority)
}

async fn card_projection(
    tx: &mut Transaction<'_, Postgres>,
    card_id: Uuid,
) -> anyhow::Result<Value> {
    let value = sqlx::query_scalar::<_, Value>(
        r#"
        select jsonb_build_object(
          'columnId', column_id::text,
          'parentCardId', parent_card_id::text,
          'title', title,
          'description', description,
          'priority', priority,
          'position', position::double precision,
          'startAt', case when start_at is null then null else to_char(start_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
          'dueAt', case when due_at is null then null else to_char(due_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
          'isArchived', archived_at is not null
        )
        from cards where id = $1
        "#,
    )
    .bind(card_id)
    .fetch_one(&mut **tx)
    .await?;
    Ok(value)
}

fn actual_card_changes(before: &Value, after: &Value, winning_fields: &[String]) -> Vec<String> {
    winning_fields
        .iter()
        .filter(|field| field.as_str() != "checklists")
        .filter(|field| before.get(field.as_str()) != after.get(field.as_str()))
        .cloned()
        .collect()
}

async fn apply_checklist_bundle(
    tx: &mut Transaction<'_, Postgres>,
    card_id: Uuid,
    checklists: &Value,
) -> anyhow::Result<()> {
    let values = checklists
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("checklists payload must be an array"))?;
    for checklist in values {
        let checklist_id = Uuid::parse_str(
            string_field(checklist, "id")
                .ok_or_else(|| anyhow::anyhow!("checklist id is missing"))?,
        )?;
        let checklist_card_id = Uuid::parse_str(
            string_field(checklist, "cardId")
                .ok_or_else(|| anyhow::anyhow!("checklist card id is missing"))?,
        )?;
        if checklist_card_id != card_id {
            anyhow::bail!("checklist payload scope mismatch");
        }
        let title = string_field(checklist, "title")
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow::anyhow!("checklist title is missing"))?;
        let position = finite_number(checklist, "position", 1_000.0)?;
        let belongs_elsewhere = sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from checklists where id = $1 and card_id <> $2)",
        )
        .bind(checklist_id)
        .bind(card_id)
        .fetch_one(&mut **tx)
        .await?;
        if belongs_elsewhere {
            anyhow::bail!("checklist id belongs to another card");
        }
        sqlx::query(
            r#"
            insert into checklists (id, card_id, title, position)
            values ($1, $2, $3, $4)
            on conflict (id) do nothing
            "#,
        )
        .bind(checklist_id)
        .bind(card_id)
        .bind(title)
        .bind(position)
        .execute(&mut **tx)
        .await?;

        let items = checklist
            .get("items")
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow::anyhow!("checklist items must be an array"))?;
        for item in items {
            let item_id = Uuid::parse_str(
                string_field(item, "id")
                    .ok_or_else(|| anyhow::anyhow!("checklist item id is missing"))?,
            )?;
            let item_checklist_id = Uuid::parse_str(
                string_field(item, "checklistId")
                    .ok_or_else(|| anyhow::anyhow!("checklist item checklist id is missing"))?,
            )?;
            if item_checklist_id != checklist_id {
                anyhow::bail!("checklist item payload scope mismatch");
            }
            let item_title = string_field(item, "title")
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| anyhow::anyhow!("checklist item title is missing"))?;
            let item_position = finite_number(item, "position", 1_000.0)?;
            let is_done = item
                .get("isDone")
                .and_then(Value::as_bool)
                .ok_or_else(|| anyhow::anyhow!("checklist item state is missing"))?;
            let belongs_elsewhere = sqlx::query_scalar::<_, bool>(
                "select exists(select 1 from checklist_items where id = $1 and checklist_id <> $2)",
            )
            .bind(item_id)
            .bind(checklist_id)
            .fetch_one(&mut **tx)
            .await?;
            if belongs_elsewhere {
                anyhow::bail!("checklist item id belongs to another checklist");
            }
            sqlx::query(
                r#"
                insert into checklist_items (
                  id, checklist_id, title, is_done, position, completed_at
                ) values (
                  $1, $2, $3, $4, $5, case when $4 then now() else null end
                )
                on conflict (id) do nothing
                "#,
            )
            .bind(item_id)
            .bind(checklist_id)
            .bind(item_title)
            .bind(is_done)
            .bind(item_position)
            .execute(&mut **tx)
            .await?;
        }
        // Legacy v1 snapshots only fill missing rows. Absence and conflicting
        // values are not authoritative because an older full snapshot may
        // arrive after a newer checklist change.
    }
    Ok(())
}

async fn roaming_field_wins(
    tx: &mut Transaction<'_, Postgres>,
    workspace_id: Uuid,
    entity_id: Uuid,
    field_name: &str,
    logical_clock: i64,
    replica_id: Uuid,
    event_id: Uuid,
) -> anyhow::Result<bool> {
    let current = sqlx::query(
        "select logical_clock, replica_id, event_id from roaming_field_versions where workspace_id = $1 and entity_id = $2 and field_name = $3",
    )
    .bind(workspace_id)
    .bind(entity_id)
    .bind(field_name)
    .fetch_optional(&mut **tx)
    .await?;
    Ok(current.map_or(true, |row| {
        let current_clock: i64 = row.try_get("logical_clock").unwrap_or(0);
        let current_replica: Uuid = row.try_get("replica_id").unwrap_or(Uuid::nil());
        let current_event: Uuid = row.try_get("event_id").unwrap_or(Uuid::nil());
        (logical_clock, replica_id, event_id) > (current_clock, current_replica, current_event)
    }))
}

async fn store_roaming_field_version(
    tx: &mut Transaction<'_, Postgres>,
    workspace_id: Uuid,
    entity_id: Uuid,
    field_name: &str,
    logical_clock: i64,
    replica_id: Uuid,
    event_id: Uuid,
) -> anyhow::Result<()> {
    sqlx::query(
        r#"
        insert into roaming_field_versions (
          workspace_id, entity_id, field_name, logical_clock, replica_id, event_id
        ) values ($1,$2,$3,$4,$5,$6)
        on conflict (workspace_id, entity_id, field_name) do update set
          logical_clock = excluded.logical_clock,
          replica_id = excluded.replica_id,
          event_id = excluded.event_id,
          updated_at = now()
        "#,
    )
    .bind(workspace_id)
    .bind(entity_id)
    .bind(field_name)
    .bind(logical_clock)
    .bind(replica_id)
    .bind(event_id)
    .execute(&mut **tx)
    .await?;
    Ok(())
}

async fn record_roaming_child_activity(
    tx: &mut Transaction<'_, Postgres>,
    workspace_id: Uuid,
    board_id: Uuid,
    card_id: Uuid,
    actor_user_id: Uuid,
    kind: &str,
    entity_type: &str,
    entity_id: Uuid,
    field_mask: &[String],
    event: &RoamingBoardEvent,
) -> anyhow::Result<()> {
    sqlx::query(
        r#"
        insert into activity_entries (
          id, workspace_id, board_id, card_id, actor_user_id, kind,
          entity_type, entity_id, field_mask, payload_jsonb
        ) values (
          gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9
        )
        "#,
    )
    .bind(workspace_id)
    .bind(board_id)
    .bind(card_id)
    .bind(actor_user_id)
    .bind(kind)
    .bind(entity_type)
    .bind(entity_id)
    .bind(field_mask)
    .bind(json!({
        "source": "roaming",
        "eventId": event.event_id,
        "replicaId": event.replica_id,
    }))
    .execute(&mut **tx)
    .await?;
    Ok(())
}

fn delta_field_mask(delta: &Value) -> Vec<String> {
    delta
        .get("fieldMask")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect()
}

async fn apply_remote_checklist_delta(
    pool: &PgPool,
    workspace_id: Uuid,
    recovered: &RecoveredRoamingEvent,
    event_id: Uuid,
    board_id: Uuid,
    card_id: Uuid,
    replica_id: Uuid,
    delta: &Value,
) -> anyhow::Result<()> {
    let event = &recovered.event;
    let delta_card_id = Uuid::parse_str(
        string_field(delta, "cardId").ok_or_else(|| anyhow::anyhow!("delta cardId is missing"))?,
    )?;
    if delta_card_id != card_id {
        anyhow::bail!("checklist delta card scope mismatch");
    }
    let card_matches = sqlx::query_scalar::<_, bool>(
        r#"
        select exists(
          select 1 from cards
          where id = $1 and board_id = $2 and deleted_at is null
        )
        "#,
    )
    .bind(card_id)
    .bind(board_id)
    .fetch_one(pool)
    .await?;
    if !card_matches {
        anyhow::bail!("checklist delta card is missing");
    }

    let owner_user_id =
        sqlx::query_scalar::<_, Uuid>("select owner_user_id from workspaces where id = $1")
            .bind(workspace_id)
            .fetch_one(pool)
            .await?;
    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        insert into roaming_board_events (
          event_id, nostr_event_id, author_public_key, workspace_id, board_id,
          replica_id, replica_seq, logical_clock, entity_id, operation, status
        ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'applied')
        "#,
    )
    .bind(event_id)
    .bind(&recovered.nostr_event_id)
    .bind(&recovered.author_public_key)
    .bind(workspace_id)
    .bind(board_id)
    .bind(replica_id)
    .bind(event.replica_seq)
    .bind(event.logical_clock)
    .bind(card_id)
    .bind(&event.operation)
    .execute(&mut *tx)
    .await?;

    let kind = string_field(delta, "kind")
        .ok_or_else(|| anyhow::anyhow!("checklist delta kind is missing"))?;
    let requested = delta_field_mask(delta);
    let requests_all = requested.iter().any(|field| field == "*");
    let requests = |field: &str| requests_all || requested.iter().any(|value| value == field);
    let mut activity_kind: Option<&str> = None;
    let mut activity_entity_type = "checklist";
    let activity_entity_id: Uuid;
    let mut changed_fields = Vec::new();
    let mut version_fields = Vec::new();

    match kind {
        "checklist.put" => {
            let checklist = delta
                .get("checklist")
                .ok_or_else(|| anyhow::anyhow!("checklist delta payload is missing"))?;
            let checklist_id = Uuid::parse_str(
                string_field(delta, "checklistId")
                    .ok_or_else(|| anyhow::anyhow!("delta checklistId is missing"))?,
            )?;
            let expected_checklist_id = checklist_id.to_string();
            let expected_card_id = card_id.to_string();
            if string_field(checklist, "id") != Some(expected_checklist_id.as_str())
                || string_field(checklist, "cardId") != Some(expected_card_id.as_str())
            {
                anyhow::bail!("checklist delta payload scope mismatch");
            }
            let title = string_field(checklist, "title")
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| anyhow::anyhow!("checklist title is missing"))?;
            let position = finite_number(checklist, "position", 1_000.0)?;
            let existing = sqlx::query(
                "select card_id, title, position::double precision as position, deleted_at is not null as deleted from checklists where id = $1",
            )
            .bind(checklist_id)
            .fetch_optional(&mut *tx)
            .await?;
            if existing
                .as_ref()
                .is_some_and(|row| row.try_get::<Uuid, _>("card_id").ok() != Some(card_id))
            {
                anyhow::bail!("checklist id belongs to another card");
            }
            let lifecycle_requested = requests_all || existing.is_none();
            let lifecycle_wins = lifecycle_requested
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    checklist_id,
                    "checklist.__lifecycle",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let title_wins = requests("title")
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    checklist_id,
                    "checklist.title",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let position_wins = requests("position")
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    checklist_id,
                    "checklist.position",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let was_deleted = existing
                .as_ref()
                .and_then(|row| row.try_get::<bool, _>("deleted").ok())
                .unwrap_or(false);
            if existing.is_none() && lifecycle_wins {
                sqlx::query(
                    "insert into checklists (id, card_id, title, position) values ($1,$2,$3,$4)",
                )
                .bind(checklist_id)
                .bind(card_id)
                .bind(title)
                .bind(position)
                .execute(&mut *tx)
                .await?;
                activity_kind = Some("checklist.created");
                changed_fields.push("title".to_string());
            } else if existing.is_some() && (!was_deleted || lifecycle_wins) {
                let before_title: String = existing.as_ref().unwrap().try_get("title")?;
                let before_position: f64 = existing.as_ref().unwrap().try_get("position")?;
                sqlx::query(
                    r#"
                    update checklists set
                      title = case when $2 then $3 else title end,
                      position = case when $4 then $5 else position end,
                      deleted_at = case when $6 then null else deleted_at end
                    where id = $1 and card_id = $7
                    "#,
                )
                .bind(checklist_id)
                .bind(title_wins)
                .bind(title)
                .bind(position_wins)
                .bind(position)
                .bind(lifecycle_wins)
                .bind(card_id)
                .execute(&mut *tx)
                .await?;
                if was_deleted && lifecycle_wins {
                    activity_kind = Some("checklist.created");
                    changed_fields.push("title".to_string());
                } else {
                    if title_wins && before_title != title {
                        changed_fields.push("title".to_string());
                    }
                    if position_wins && (before_position - position).abs() > f64::EPSILON {
                        changed_fields.push("position".to_string());
                    }
                    if !changed_fields.is_empty() {
                        activity_kind = Some("checklist.updated");
                    }
                }
            }
            if lifecycle_wins {
                version_fields.push("checklist.__lifecycle");
            }
            if title_wins {
                version_fields.push("checklist.title");
            }
            if position_wins {
                version_fields.push("checklist.position");
            }
            activity_entity_id = checklist_id;
        }
        "checklist.delete" => {
            let checklist_id = Uuid::parse_str(
                string_field(delta, "checklistId")
                    .ok_or_else(|| anyhow::anyhow!("delta checklistId is missing"))?,
            )?;
            let wins = roaming_field_wins(
                &mut tx,
                workspace_id,
                checklist_id,
                "checklist.__lifecycle",
                event.logical_clock,
                replica_id,
                event_id,
            )
            .await?;
            if wins {
                let affected = sqlx::query(
                    "update checklists set deleted_at = now() where id = $1 and card_id = $2 and deleted_at is null",
                )
                .bind(checklist_id)
                .bind(card_id)
                .execute(&mut *tx)
                .await?
                .rows_affected();
                if affected > 0 {
                    sqlx::query(
                        "update checklist_items set deleted_at = now() where checklist_id = $1 and deleted_at is null",
                    )
                    .bind(checklist_id)
                    .execute(&mut *tx)
                    .await?;
                    activity_kind = Some("checklist.deleted");
                }
                version_fields.push("checklist.__lifecycle");
            }
            activity_entity_id = checklist_id;
        }
        "checklist_item.put" => {
            activity_entity_type = "checklist_item";
            let checklist_id = Uuid::parse_str(
                string_field(delta, "checklistId")
                    .ok_or_else(|| anyhow::anyhow!("delta checklistId is missing"))?,
            )?;
            let item_id = Uuid::parse_str(
                string_field(delta, "itemId")
                    .ok_or_else(|| anyhow::anyhow!("delta itemId is missing"))?,
            )?;
            let item = delta
                .get("item")
                .ok_or_else(|| anyhow::anyhow!("checklist item delta payload is missing"))?;
            let expected_item_id = item_id.to_string();
            let expected_checklist_id = checklist_id.to_string();
            if string_field(item, "id") != Some(expected_item_id.as_str())
                || string_field(item, "checklistId") != Some(expected_checklist_id.as_str())
            {
                anyhow::bail!("checklist item delta payload scope mismatch");
            }
            let checklist_matches = sqlx::query_scalar::<_, bool>(
                "select exists(select 1 from checklists where id = $1 and card_id = $2 and deleted_at is null)",
            )
            .bind(checklist_id)
            .bind(card_id)
            .fetch_one(&mut *tx)
            .await?;
            if !checklist_matches {
                anyhow::bail!("checklist item delta parent is missing");
            }
            let title = string_field(item, "title")
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| anyhow::anyhow!("checklist item title is missing"))?;
            let position = finite_number(item, "position", 1_000.0)?;
            let is_done = item
                .get("isDone")
                .and_then(Value::as_bool)
                .ok_or_else(|| anyhow::anyhow!("checklist item state is missing"))?;
            let existing = sqlx::query(
                "select checklist_id, title, position::double precision as position, is_done, deleted_at is not null as deleted from checklist_items where id = $1",
            )
            .bind(item_id)
            .fetch_optional(&mut *tx)
            .await?;
            if existing.as_ref().is_some_and(|row| {
                row.try_get::<Uuid, _>("checklist_id").ok() != Some(checklist_id)
            }) {
                anyhow::bail!("checklist item id belongs to another checklist");
            }
            let lifecycle_requested = requests_all || existing.is_none();
            let lifecycle_wins = lifecycle_requested
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    item_id,
                    "checklist_item.__lifecycle",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let title_wins = requests("title")
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    item_id,
                    "checklist_item.title",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let position_wins = requests("position")
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    item_id,
                    "checklist_item.position",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let done_wins = requests("isDone")
                && roaming_field_wins(
                    &mut tx,
                    workspace_id,
                    item_id,
                    "checklist_item.isDone",
                    event.logical_clock,
                    replica_id,
                    event_id,
                )
                .await?;
            let was_deleted = existing
                .as_ref()
                .and_then(|row| row.try_get::<bool, _>("deleted").ok())
                .unwrap_or(false);
            if existing.is_none() && lifecycle_wins {
                sqlx::query(
                    r#"
                    insert into checklist_items (
                      id, checklist_id, title, is_done, position, completed_at
                    ) values ($1,$2,$3,$4,$5,case when $4 then now() else null end)
                    "#,
                )
                .bind(item_id)
                .bind(checklist_id)
                .bind(title)
                .bind(is_done)
                .bind(position)
                .execute(&mut *tx)
                .await?;
                activity_kind = Some("checklist_item.created");
                changed_fields.push("title".to_string());
            } else if existing.is_some() && (!was_deleted || lifecycle_wins) {
                let row = existing.as_ref().unwrap();
                let before_title: String = row.try_get("title")?;
                let before_position: f64 = row.try_get("position")?;
                let before_done: bool = row.try_get("is_done")?;
                sqlx::query(
                    r#"
                    update checklist_items set
                      title = case when $2 then $3 else title end,
                      position = case when $4 then $5 else position end,
                      is_done = case when $6 then $7 else is_done end,
                      completed_at = case
                        when $6 and $7 then coalesce(completed_at, now())
                        when $6 then null
                        else completed_at
                      end,
                      deleted_at = case when $8 then null else deleted_at end
                    where id = $1 and checklist_id = $9
                    "#,
                )
                .bind(item_id)
                .bind(title_wins)
                .bind(title)
                .bind(position_wins)
                .bind(position)
                .bind(done_wins)
                .bind(is_done)
                .bind(lifecycle_wins)
                .bind(checklist_id)
                .execute(&mut *tx)
                .await?;
                if was_deleted && lifecycle_wins {
                    activity_kind = Some("checklist_item.created");
                    changed_fields.push("title".to_string());
                } else {
                    if title_wins && before_title != title {
                        changed_fields.push("title".to_string());
                    }
                    if position_wins && (before_position - position).abs() > f64::EPSILON {
                        changed_fields.push("position".to_string());
                    }
                    if done_wins && before_done != is_done {
                        changed_fields.push("isDone".to_string());
                        activity_kind = Some(if is_done {
                            "checklist_item.completed"
                        } else {
                            "checklist_item.reopened"
                        });
                    } else if !changed_fields.is_empty() {
                        activity_kind = Some("checklist_item.updated");
                    }
                }
            }
            if lifecycle_wins {
                version_fields.push("checklist_item.__lifecycle");
            }
            if title_wins {
                version_fields.push("checklist_item.title");
            }
            if position_wins {
                version_fields.push("checklist_item.position");
            }
            if done_wins {
                version_fields.push("checklist_item.isDone");
            }
            activity_entity_id = item_id;
        }
        "checklist_item.delete" => {
            activity_entity_type = "checklist_item";
            let item_id = Uuid::parse_str(
                string_field(delta, "itemId")
                    .ok_or_else(|| anyhow::anyhow!("delta itemId is missing"))?,
            )?;
            let wins = roaming_field_wins(
                &mut tx,
                workspace_id,
                item_id,
                "checklist_item.__lifecycle",
                event.logical_clock,
                replica_id,
                event_id,
            )
            .await?;
            if wins {
                let affected = sqlx::query(
                    r#"
                    update checklist_items chi set deleted_at = now()
                    from checklists ch
                    where chi.id = $1
                      and chi.checklist_id = ch.id
                      and ch.card_id = $2
                      and chi.deleted_at is null
                    "#,
                )
                .bind(item_id)
                .bind(card_id)
                .execute(&mut *tx)
                .await?
                .rows_affected();
                if affected > 0 {
                    activity_kind = Some("checklist_item.deleted");
                }
                version_fields.push("checklist_item.__lifecycle");
            }
            activity_entity_id = item_id;
        }
        _ => anyhow::bail!("unsupported checklist delta kind"),
    }

    for field in version_fields {
        store_roaming_field_version(
            &mut tx,
            workspace_id,
            activity_entity_id,
            field,
            event.logical_clock,
            replica_id,
            event_id,
        )
        .await?;
    }
    if let Some(activity_kind) = activity_kind {
        record_roaming_child_activity(
            &mut tx,
            workspace_id,
            board_id,
            card_id,
            owner_user_id,
            activity_kind,
            activity_entity_type,
            activity_entity_id,
            &changed_fields,
            event,
        )
        .await?;
    }
    sqlx::query("update roaming_board_events set applied_at = now() where event_id = $1")
        .bind(event_id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(())
}

async fn apply_remote_card_delete(
    pool: &PgPool,
    workspace_id: Uuid,
    recovered: &RecoveredRoamingEvent,
    event_id: Uuid,
    board_id: Uuid,
    entity_id: Uuid,
    replica_id: Uuid,
) -> anyhow::Result<()> {
    let event = &recovered.event;
    let existing_board_id =
        sqlx::query_scalar::<_, Uuid>("select board_id from cards where id = $1")
            .bind(entity_id)
            .fetch_optional(pool)
            .await?;
    if existing_board_id.is_some_and(|value| value != board_id) {
        anyhow::bail!("card id belongs to another board");
    }

    let deleted_at = event
        .payload
        .get("deletedAt")
        .and_then(Value::as_str)
        .unwrap_or(event.occurred_at.as_str());
    let owner_user_id =
        sqlx::query_scalar::<_, Uuid>("select owner_user_id from workspaces where id = $1")
            .bind(workspace_id)
            .fetch_one(pool)
            .await?;

    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        insert into roaming_board_events (
          event_id, nostr_event_id, author_public_key, workspace_id, board_id,
          replica_id, replica_seq, logical_clock, entity_id, operation, status
        ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'applied')
        "#,
    )
    .bind(event_id)
    .bind(&recovered.nostr_event_id)
    .bind(&recovered.author_public_key)
    .bind(workspace_id)
    .bind(board_id)
    .bind(replica_id)
    .bind(event.replica_seq)
    .bind(event.logical_clock)
    .bind(entity_id)
    .bind(&event.operation)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        r#"
        update cards
        set
          deleted_at = greatest(coalesce(deleted_at, $2::timestamptz), $2::timestamptz),
          updated_at = greatest(updated_at, $2::timestamptz)
        where id = $1 and board_id = $3
        "#,
    )
    .bind(entity_id)
    .bind(deleted_at)
    .bind(board_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        r#"
        insert into tombstones (
          id, workspace_id, entity_type, entity_id,
          deleted_at, metadata_jsonb
        ) values (
          gen_random_uuid(), $1, 'card', $2, $3::timestamptz,
          jsonb_build_object(
            'boardId', $4,
            'scope', 'all_devices',
            'source', 'roaming',
            'eventId', $5,
            'replicaId', $6
          )
        )
        on conflict (entity_type, entity_id) do update set
          workspace_id = excluded.workspace_id,
          deleted_at = greatest(tombstones.deleted_at, excluded.deleted_at),
          metadata_jsonb = tombstones.metadata_jsonb || excluded.metadata_jsonb
        "#,
    )
    .bind(workspace_id)
    .bind(entity_id)
    .bind(deleted_at)
    .bind(board_id)
    .bind(event_id)
    .bind(replica_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        r#"
        insert into roaming_field_versions (
          workspace_id, entity_id, field_name, logical_clock, replica_id, event_id
        ) values ($1,$2,'__lifecycle',$3,$4,$5)
        on conflict (workspace_id, entity_id, field_name) do update set
          logical_clock = greatest(roaming_field_versions.logical_clock, excluded.logical_clock),
          replica_id = case
            when excluded.logical_clock >= roaming_field_versions.logical_clock then excluded.replica_id
            else roaming_field_versions.replica_id
          end,
          event_id = case
            when excluded.logical_clock >= roaming_field_versions.logical_clock then excluded.event_id
            else roaming_field_versions.event_id
          end,
          updated_at = now()
        "#,
    )
    .bind(workspace_id)
    .bind(entity_id)
    .bind(event.logical_clock)
    .bind(replica_id)
    .bind(event_id)
    .execute(&mut *tx)
    .await?;

    sqlx::query(
        r#"
        insert into activity_entries (
          id, workspace_id, board_id, card_id, actor_user_id, kind,
          entity_type, entity_id, field_mask, payload_jsonb
        ) values (
          gen_random_uuid(), $1, $2, $3, $4, 'card.deleted',
          'card', $5, array['__lifecycle'], $6
        )
        "#,
    )
    .bind(workspace_id)
    .bind(board_id)
    .bind(existing_board_id.map(|_| entity_id))
    .bind(owner_user_id)
    .bind(entity_id)
    .bind(json!({
        "source": "roaming",
        "scope": "all_devices",
        "eventId": event.event_id,
        "replicaId": event.replica_id,
    }))
    .execute(&mut *tx)
    .await?;

    sqlx::query("update roaming_board_events set applied_at = now() where event_id = $1")
        .bind(event_id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(())
}

#[derive(Debug)]
struct RoamingBoardAppearance {
    theme_preset: String,
    wallpaper_kind: String,
    wallpaper_value: Option<String>,
    column_density: String,
    card_preview_mode: String,
    show_card_description: bool,
    show_card_dates: bool,
    show_checklist_progress: bool,
    custom_properties: Value,
}

fn required_bool(value: &Value, field: &str) -> anyhow::Result<bool> {
    value
        .get(field)
        .and_then(Value::as_bool)
        .ok_or_else(|| anyhow::anyhow!("appearance.{field} must be boolean"))
}

fn parse_roaming_board_appearance(
    event: &RoamingBoardEvent,
) -> anyhow::Result<RoamingBoardAppearance> {
    let value = event
        .payload
        .get("appearance")
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow::anyhow!("appearance payload is missing"))?;
    if value.get("boardId").and_then(Value::as_str) != Some(event.board_id.as_str()) {
        anyhow::bail!("appearance payload scope mismatch");
    }

    let theme_preset = value
        .get("themePreset")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|candidate| !candidate.is_empty() && candidate.len() <= 100)
        .ok_or_else(|| anyhow::anyhow!("appearance.themePreset is invalid"))?
        .to_string();
    let wallpaper = value
        .get("wallpaper")
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow::anyhow!("appearance.wallpaper is missing"))?;
    let wallpaper_kind = wallpaper
        .get("kind")
        .and_then(Value::as_str)
        .filter(|kind| {
            matches!(
                *kind,
                "none" | "accent" | "solid" | "gradient" | "preset" | "image"
            )
        })
        .ok_or_else(|| anyhow::anyhow!("appearance.wallpaper.kind is invalid"))?
        .to_string();
    let raw_wallpaper_value = wallpaper
        .get("value")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|candidate| !candidate.is_empty())
        .map(str::to_string);
    let wallpaper_value = match wallpaper_kind.as_str() {
        "none" | "accent" => None,
        "image" => {
            let candidate = raw_wallpaper_value
                .filter(|candidate| {
                    candidate.len() <= 2_048
                        && !candidate.contains('\r')
                        && !candidate.contains('\n')
                        && (candidate.starts_with("https://") || candidate.starts_with("http://"))
                })
                .ok_or_else(|| anyhow::anyhow!("appearance image URL is invalid"))?;
            Some(candidate)
        }
        _ => Some(
            raw_wallpaper_value
                .filter(|candidate| candidate.len() <= 4_096)
                .ok_or_else(|| anyhow::anyhow!("appearance wallpaper value is invalid"))?,
        ),
    };
    let column_density = value
        .get("columnDensity")
        .and_then(Value::as_str)
        .filter(|candidate| matches!(*candidate, "comfortable" | "compact"))
        .ok_or_else(|| anyhow::anyhow!("appearance.columnDensity is invalid"))?
        .to_string();
    let card_preview_mode = value
        .get("cardPreviewMode")
        .and_then(Value::as_str)
        .filter(|candidate| matches!(*candidate, "compact" | "expanded"))
        .ok_or_else(|| anyhow::anyhow!("appearance.cardPreviewMode is invalid"))?
        .to_string();
    let custom_properties = value
        .get("customProperties")
        .filter(|candidate| candidate.is_object())
        .cloned()
        .unwrap_or_else(|| json!({}));
    if let Some(accent) = custom_properties.get("accentColor").and_then(Value::as_str) {
        if accent.len() != 7
            || !accent.starts_with('#')
            || !accent[1..]
                .chars()
                .all(|character| character.is_ascii_hexdigit())
        {
            anyhow::bail!("appearance.customProperties.accentColor is invalid");
        }
    }

    Ok(RoamingBoardAppearance {
        theme_preset,
        wallpaper_kind,
        wallpaper_value,
        column_density,
        card_preview_mode,
        show_card_description: required_bool(&Value::Object(value.clone()), "showCardDescription")?,
        show_card_dates: required_bool(&Value::Object(value.clone()), "showCardDates")?,
        show_checklist_progress: required_bool(
            &Value::Object(value.clone()),
            "showChecklistProgress",
        )?,
        custom_properties,
    })
}

async fn appearance_projection(
    tx: &mut Transaction<'_, Postgres>,
    board_id: Uuid,
) -> anyhow::Result<Value> {
    Ok(sqlx::query_scalar::<_, Value>(
        r#"
        select jsonb_build_object(
          'boardId', b.id::text,
          'isCustomized', a.board_id is not null,
          'themePreset', coalesce(a.theme_preset, 'system'),
          'wallpaper', jsonb_build_object(
            'kind', coalesce(a.wallpaper_kind, 'none'),
            'value', a.wallpaper_value
          ),
          'columnDensity', coalesce(a.column_density, 'comfortable'),
          'cardPreviewMode', coalesce(a.card_preview_mode, 'expanded'),
          'showCardDescription', coalesce(a.show_card_description, true),
          'showCardDates', coalesce(a.show_card_dates, true),
          'showChecklistProgress', coalesce(a.show_checklist_progress, true),
          'customProperties', coalesce(a.custom_properties_jsonb, '{}'::jsonb)
        )
        from boards b
        left join board_appearance_settings a on a.board_id = b.id
        where b.id = $1 and b.deleted_at is null
        "#,
    )
    .bind(board_id)
    .fetch_one(&mut **tx)
    .await?)
}

async fn apply_remote_board_appearance(
    pool: &PgPool,
    workspace_id: Uuid,
    recovered: &RecoveredRoamingEvent,
    event_id: Uuid,
    board_id: Uuid,
    replica_id: Uuid,
) -> anyhow::Result<()> {
    let event = &recovered.event;
    let appearance = parse_roaming_board_appearance(event)?;
    let owner_user_id =
        sqlx::query_scalar::<_, Uuid>("select owner_user_id from workspaces where id = $1")
            .bind(workspace_id)
            .fetch_one(pool)
            .await?;
    let mut tx = pool.begin().await?;
    let before = appearance_projection(&mut tx, board_id).await?;

    sqlx::query(
        r#"
        insert into roaming_board_events (
          event_id, nostr_event_id, author_public_key, workspace_id, board_id,
          replica_id, replica_seq, logical_clock, entity_id, operation, status
        ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'applied')
        "#,
    )
    .bind(event_id)
    .bind(&recovered.nostr_event_id)
    .bind(&recovered.author_public_key)
    .bind(workspace_id)
    .bind(board_id)
    .bind(replica_id)
    .bind(event.replica_seq)
    .bind(event.logical_clock)
    .bind(board_id)
    .bind(&event.operation)
    .execute(&mut *tx)
    .await?;

    if roaming_field_wins(
        &mut tx,
        workspace_id,
        board_id,
        "appearance",
        event.logical_clock,
        replica_id,
        event_id,
    )
    .await?
    {
        sqlx::query(
            r#"
            insert into board_appearance_settings (
              board_id, theme_preset, wallpaper_kind, wallpaper_value,
              column_density, card_preview_mode, show_card_description,
              show_card_dates, show_checklist_progress, custom_properties_jsonb
            ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            on conflict (board_id) do update set
              theme_preset = excluded.theme_preset,
              wallpaper_kind = excluded.wallpaper_kind,
              wallpaper_value = excluded.wallpaper_value,
              column_density = excluded.column_density,
              card_preview_mode = excluded.card_preview_mode,
              show_card_description = excluded.show_card_description,
              show_card_dates = excluded.show_card_dates,
              show_checklist_progress = excluded.show_checklist_progress,
              custom_properties_jsonb = excluded.custom_properties_jsonb,
              updated_at = now()
            "#,
        )
        .bind(board_id)
        .bind(&appearance.theme_preset)
        .bind(&appearance.wallpaper_kind)
        .bind(&appearance.wallpaper_value)
        .bind(&appearance.column_density)
        .bind(&appearance.card_preview_mode)
        .bind(appearance.show_card_description)
        .bind(appearance.show_card_dates)
        .bind(appearance.show_checklist_progress)
        .bind(&appearance.custom_properties)
        .execute(&mut *tx)
        .await?;
        store_roaming_field_version(
            &mut tx,
            workspace_id,
            board_id,
            "appearance",
            event.logical_clock,
            replica_id,
            event_id,
        )
        .await?;

        let after = appearance_projection(&mut tx, board_id).await?;
        if before != after {
            sqlx::query(
                r#"
                insert into activity_entries (
                  id, workspace_id, board_id, card_id, actor_user_id, kind,
                  entity_type, entity_id, field_mask, payload_jsonb
                ) values (
                  gen_random_uuid(), $1, $2, null, $3, 'board.appearance.updated',
                  'board', $2, array['appearance'], $4
                )
                "#,
            )
            .bind(workspace_id)
            .bind(board_id)
            .bind(owner_user_id)
            .bind(json!({
                "source": "roaming",
                "eventId": event.event_id,
                "replicaId": event.replica_id,
                "changes": {"appearance": {"before": before, "after": after}},
            }))
            .execute(&mut *tx)
            .await?;
        }
    }

    sqlx::query("update roaming_board_events set applied_at = now() where event_id = $1")
        .bind(event_id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(())
}

async fn apply_remote_event(
    pool: &PgPool,
    workspace_id: Uuid,
    recovered: &RecoveredRoamingEvent,
) -> anyhow::Result<()> {
    let event = &recovered.event;
    if event.operation == "board.snapshot" {
        return Ok(());
    }
    if event.workspace_id != workspace_id.to_string() {
        anyhow::bail!("unsupported roaming event shape");
    }
    let event_id = Uuid::parse_str(&event.event_id)?;
    let board_id = Uuid::parse_str(&event.board_id)?;
    let entity_id = Uuid::parse_str(&event.entity_id)?;
    let replica_id = Uuid::parse_str(&event.replica_id)?;
    let exists = sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from roaming_board_events where event_id = $1)",
    )
    .bind(event_id)
    .fetch_one(pool)
    .await?;
    if exists {
        return Ok(());
    }
    let board_matches = sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from boards where id = $1 and workspace_id = $2 and deleted_at is null)",
    )
    .bind(board_id)
    .bind(workspace_id)
    .fetch_one(pool)
    .await?;
    if !board_matches {
        anyhow::bail!("board does not belong to roaming workspace");
    }

    if event.operation == "board.appearance.put" {
        if event.entity_type != "board" || entity_id != board_id {
            anyhow::bail!("unsupported roaming board event shape");
        }
        return apply_remote_board_appearance(
            pool,
            workspace_id,
            recovered,
            event_id,
            board_id,
            replica_id,
        )
        .await;
    }

    if event.entity_type != "card"
        || !matches!(event.operation.as_str(), "card.put" | "card.delete")
    {
        anyhow::bail!("unsupported roaming card event shape");
    }

    if event.operation == "card.delete" {
        return apply_remote_card_delete(
            pool,
            workspace_id,
            recovered,
            event_id,
            board_id,
            entity_id,
            replica_id,
        )
        .await;
    }

    let tombstoned = sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from tombstones where entity_type = 'card' and entity_id = $1)",
    )
    .bind(entity_id)
    .fetch_one(pool)
    .await?;
    if tombstoned {
        sqlx::query(
            r#"
            insert into roaming_board_events (
              event_id, nostr_event_id, author_public_key, workspace_id, board_id,
              replica_id, replica_seq, logical_clock, entity_id, operation, status, error
            ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'rejected','tombstone_wins')
            "#,
        )
        .bind(event_id)
        .bind(&recovered.nostr_event_id)
        .bind(&recovered.author_public_key)
        .bind(workspace_id)
        .bind(board_id)
        .bind(replica_id)
        .bind(event.replica_seq)
        .bind(event.logical_clock)
        .bind(entity_id)
        .bind(&event.operation)
        .execute(pool)
        .await?;
        return Ok(());
    }

    if let Some(delta) = event.payload.get(CHECKLIST_DELTA_KEY) {
        return apply_remote_checklist_delta(
            pool,
            workspace_id,
            recovered,
            event_id,
            board_id,
            entity_id,
            replica_id,
            delta,
        )
        .await;
    }

    let card = event
        .payload
        .get("card")
        .ok_or_else(|| anyhow::anyhow!("card payload is missing"))?;
    if string_field(card, "id") != Some(event.entity_id.as_str())
        || string_field(card, "boardId") != Some(event.board_id.as_str())
    {
        anyhow::bail!("card payload scope mismatch");
    }
    let column_id = Uuid::parse_str(
        string_field(card, "columnId").ok_or_else(|| anyhow::anyhow!("columnId is missing"))?,
    )?;
    let column_matches = sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from board_columns where id = $1 and board_id = $2 and deleted_at is null)",
    )
    .bind(column_id)
    .bind(board_id)
    .fetch_one(pool)
    .await?;
    if !column_matches {
        anyhow::bail!("target column does not belong to board");
    }
    let card_title = string_field(card, "title")
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| anyhow::anyhow!("card title is missing"))?;
    let card_priority = normalized_card_priority(card)?;
    let card_position = finite_number(card, "position", 1_000.0)?;

    let mut tx = pool.begin().await?;
    sqlx::query(
        r#"
        insert into roaming_board_events (
          event_id, nostr_event_id, author_public_key, workspace_id, board_id,
          replica_id, replica_seq, logical_clock, entity_id, operation, status
        ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'applied')
        "#,
    )
    .bind(event_id)
    .bind(&recovered.nostr_event_id)
    .bind(&recovered.author_public_key)
    .bind(workspace_id)
    .bind(board_id)
    .bind(replica_id)
    .bind(event.replica_seq)
    .bind(event.logical_clock)
    .bind(entity_id)
    .bind(&event.operation)
    .execute(&mut *tx)
    .await?;

    let requested: HashSet<&str> = if event.field_mask.iter().any(|field| field == "*") {
        CARD_FIELDS.iter().copied().collect()
    } else {
        event.field_mask.iter().map(String::as_str).collect()
    };
    let mut winning = HashSet::new();
    for field in requested {
        if !CARD_FIELDS.contains(&field) {
            continue;
        }
        let current = sqlx::query(
            "select logical_clock, replica_id, event_id from roaming_field_versions where workspace_id = $1 and entity_id = $2 and field_name = $3",
        )
        .bind(workspace_id)
        .bind(entity_id)
        .bind(field)
        .fetch_optional(&mut *tx)
        .await?;
        let wins = current.map_or(true, |row| {
            let current_clock: i64 = row.try_get("logical_clock").unwrap_or(0);
            let current_replica: Uuid = row.try_get("replica_id").unwrap_or(Uuid::nil());
            let current_event: Uuid = row.try_get("event_id").unwrap_or(Uuid::nil());
            (event.logical_clock, replica_id, event_id)
                > (current_clock, current_replica, current_event)
        });
        if wins {
            winning.insert(field);
        }
    }

    let owner_user_id =
        sqlx::query_scalar::<_, Uuid>("select owner_user_id from workspaces where id = $1")
            .bind(workspace_id)
            .fetch_one(&mut *tx)
            .await?;
    let existing_card_board_id =
        sqlx::query_scalar::<_, Uuid>("select board_id from cards where id = $1")
            .bind(entity_id)
            .fetch_optional(&mut *tx)
            .await?;
    if existing_card_board_id.is_some_and(|existing_board_id| existing_board_id != board_id) {
        anyhow::bail!("card id belongs to another board");
    }
    let card_exists = existing_card_board_id.is_some();
    let before_card = if card_exists {
        Some(card_projection(&mut tx, entity_id).await?)
    } else {
        None
    };
    if !card_exists {
        sqlx::query(
            r#"
            insert into cards (
              id, board_id, column_id, parent_card_id, title, description,
              priority, position, start_at, due_at,
              created_by_user_id, archived_at
            ) values (
              $1,$2,$3,$4,$5,$6,$7,$8,$9::timestamptz,$10::timestamptz,
              $11,case when $12 then now() else null end
            )
            "#,
        )
        .bind(entity_id)
        .bind(board_id)
        .bind(column_id)
        .bind(
            string_field(card, "parentCardId")
                .map(Uuid::parse_str)
                .transpose()?,
        )
        .bind(card_title)
        .bind(string_field(card, "description"))
        .bind(card_priority)
        .bind(card_position)
        .bind(string_field(card, "startAt"))
        .bind(string_field(card, "dueAt"))
        .bind(owner_user_id)
        .bind(
            card.get("isArchived")
                .and_then(Value::as_bool)
                .unwrap_or(false),
        )
        .execute(&mut *tx)
        .await?;
        winning = CARD_FIELDS.iter().copied().collect();
    } else if !winning.is_empty() {
        sqlx::query(
            r#"
            update cards set
              column_id = case when $2 then $3 else column_id end,
              parent_card_id = case when $4 then $5 else parent_card_id end,
              title = case when $6 then $7 else title end,
              description = case when $8 then $9 else description end,
              priority = case when $10 then $11 else priority end,
              position = case when $12 then $13 else position end,
              start_at = case when $14 then $15::timestamptz else start_at end,
              due_at = case when $16 then $17::timestamptz else due_at end,
              archived_at = case
                when $18 and $19 then coalesce(archived_at, now())
                when $18 then null
                else archived_at
              end,
              updated_at = now()
            where id = $1 and board_id = $20 and deleted_at is null
            "#,
        )
        .bind(entity_id)
        .bind(winning.contains("columnId"))
        .bind(column_id)
        .bind(winning.contains("parentCardId"))
        .bind(
            string_field(card, "parentCardId")
                .map(Uuid::parse_str)
                .transpose()?,
        )
        .bind(winning.contains("title"))
        .bind(card_title)
        .bind(winning.contains("description"))
        .bind(string_field(card, "description"))
        .bind(winning.contains("priority"))
        .bind(card_priority)
        .bind(winning.contains("position"))
        .bind(card_position)
        .bind(winning.contains("startAt"))
        .bind(string_field(card, "startAt"))
        .bind(winning.contains("dueAt"))
        .bind(string_field(card, "dueAt"))
        .bind(winning.contains("isArchived"))
        .bind(
            card.get("isArchived")
                .and_then(Value::as_bool)
                .unwrap_or(false),
        )
        .bind(board_id)
        .execute(&mut *tx)
        .await?;
    }

    if winning.contains("checklists") {
        if let Some(checklists) = event.payload.get("checklists") {
            apply_checklist_bundle(&mut tx, entity_id, checklists).await?;
        }
    }

    let mut winning_fields = winning
        .iter()
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    winning_fields.sort();

    let after_card = card_projection(&mut tx, entity_id).await?;
    let activity_fields = if card_exists {
        actual_card_changes(
            before_card.as_ref().expect("existing card projection"),
            &after_card,
            &winning_fields,
        )
    } else {
        vec![
            "title".to_string(),
            "description".to_string(),
            "columnId".to_string(),
        ]
    };
    if !activity_fields.is_empty() {
        let activity_kind = if !card_exists {
            "card.created"
        } else if activity_fields.iter().any(|field| field == "columnId") {
            "card.moved"
        } else if activity_fields.iter().any(|field| field == "isArchived") {
            if after_card
                .get("isArchived")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                "card.archived"
            } else {
                "card.restored"
            }
        } else {
            "card.updated"
        };
        sqlx::query(
            r#"
            insert into activity_entries (
              id, workspace_id, board_id, card_id, actor_user_id, kind,
              entity_type, entity_id, field_mask, payload_jsonb
            ) values (
              gen_random_uuid(), $1, $2, $3, $4, $5,
              'card', $3, $6, $7
            )
            "#,
        )
        .bind(workspace_id)
        .bind(board_id)
        .bind(entity_id)
        .bind(owner_user_id)
        .bind(activity_kind)
        .bind(&activity_fields)
        .bind(json!({
            "source": "roaming",
            "eventId": event.event_id,
            "replicaId": event.replica_id,
            "fromColumnId": before_card.as_ref().and_then(|value| value.get("columnId")),
            "toColumnId": after_card.get("columnId"),
        }))
        .execute(&mut *tx)
        .await?;
    }

    for field in winning_fields {
        sqlx::query(
            r#"
            insert into roaming_field_versions (
              workspace_id, entity_id, field_name, logical_clock, replica_id, event_id
            ) values ($1,$2,$3,$4,$5,$6)
            on conflict (workspace_id, entity_id, field_name) do update set
              logical_clock = excluded.logical_clock,
              replica_id = excluded.replica_id,
              event_id = excluded.event_id,
              updated_at = now()
            "#,
        )
        .bind(workspace_id)
        .bind(entity_id)
        .bind(&field)
        .bind(event.logical_clock)
        .bind(replica_id)
        .bind(event_id)
        .execute(&mut *tx)
        .await?;
    }

    sqlx::query("update roaming_board_events set applied_at = now() where event_id = $1")
        .bind(event_id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;
    use uuid::Uuid;

    use super::{
        actual_card_changes, checklist_delta_from_activity, normalized_card_priority, CARD_FIELDS,
    };

    #[test]
    fn fixed_card_state_is_not_part_of_the_roaming_contract() {
        assert!(!CARD_FIELDS.contains(&"status"));
        assert!(!CARD_FIELDS.contains(&"completedAt"));
    }

    #[test]
    fn roaming_card_rejects_invalid_database_values() {
        assert!(normalized_card_priority(&json!({"priority": "maximum"})).is_err());
    }

    #[test]
    fn unchanged_column_and_checklist_snapshot_do_not_create_card_activity() {
        let before = json!({"columnId": "column-a", "title": "Задача"});
        let after = before.clone();
        let winning = vec![
            "columnId".to_string(),
            "title".to_string(),
            "checklists".to_string(),
        ];

        assert!(actual_card_changes(&before, &after, &winning).is_empty());
    }

    #[test]
    fn checklist_activity_is_encoded_as_one_entity_delta() {
        let card_id = Uuid::from_u128(1);
        let checklist_id = Uuid::from_u128(2);
        let item_id = Uuid::from_u128(3);
        let checklists = json!([{
            "id": checklist_id,
            "cardId": card_id,
            "title": "Проверки",
            "position": 1000,
            "items": [{
                "id": item_id,
                "checklistId": checklist_id,
                "title": "Первый пункт",
                "isDone": false,
                "position": 1000
            }]
        }]);

        let delta = checklist_delta_from_activity(
            "checklist_item.created",
            "checklist_item",
            item_id,
            card_id,
            &["title".to_string()],
            &checklists,
            "2026-08-13T10:00:00.000Z",
        )
        .expect("checklist item delta");

        assert_eq!(delta["kind"], "checklist_item.put");
        assert_eq!(delta["itemId"], item_id.to_string());
        assert_eq!(delta["fieldMask"], json!(["*"]));
        assert!(delta.get("checklists").is_none());
    }
}
