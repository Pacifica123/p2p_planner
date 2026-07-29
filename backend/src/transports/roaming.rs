use std::{collections::HashSet, time::Duration};

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
    "status",
    "priority",
    "position",
    "startAt",
    "dueAt",
    "completedAt",
    "isArchived",
    "checklists",
];

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
        publish_pending(&db, &transport, settings.transports.batch_size).await;
        ingest_remote(&db, &transport).await;
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
            'status', c.status,
            'priority', c.priority,
            'position', c.position::double precision,
            'startAt', case when c.start_at is null then null else to_char(c.start_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
            'dueAt', case when c.due_at is null then null else to_char(c.due_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
            'completedAt', case when c.completed_at is null then null else to_char(c.completed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') end,
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
        let event = RoamingBoardEvent {
            protocol_version: ROAMING_PROTOCOL_VERSION.to_string(),
            event_id: outbox_id.to_string(),
            workspace_id: row.try_get::<Uuid, _>("workspace_id").unwrap().to_string(),
            board_id: row.try_get::<Uuid, _>("board_id").unwrap().to_string(),
            replica_id: row.try_get::<Uuid, _>("workspace_id").unwrap().to_string(),
            replica_seq: row.try_get("event_seq").unwrap_or(1),
            logical_clock: row.try_get("logical_clock").unwrap_or(1),
            entity_type: "card".to_string(),
            entity_id: row.try_get::<Uuid, _>("card_id").unwrap().to_string(),
            operation: "card.put".to_string(),
            field_mask: vec!["*".to_string()],
            payload: json!({
                "card": row.try_get::<Value, _>("card").unwrap_or_else(|_| json!({})),
                "checklists": row.try_get::<Value, _>("checklists").unwrap_or_else(|_| json!([])),
            }),
            occurred_at: row.try_get("occurred_at").unwrap_or_default(),
        };
        match transport.publish_roaming(&event).await {
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

async fn ingest_remote(pool: &PgPool, transport: &NostrTransport) {
    let boards = match sqlx::query(
        r#"
        select b.id as board_id, b.workspace_id
        from boards b
        join workspaces w on w.id = b.workspace_id
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

    for board in boards {
        let board_id: Uuid = match board.try_get("board_id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let workspace_id: Uuid = match board.try_get("workspace_id") {
            Ok(value) => value,
            Err(_) => continue,
        };
        let events = match transport.recover_roaming(&board_id.to_string()).await {
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
        let checklist_exists = sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from checklists where id = $1 and card_id = $2 and deleted_at is null)",
        )
        .bind(checklist_id)
        .bind(card_id)
        .fetch_one(&mut **tx)
        .await?;
        if !checklist_exists {
            anyhow::bail!("checklist does not belong to card");
        }
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
            let is_done = item
                .get("isDone")
                .and_then(Value::as_bool)
                .ok_or_else(|| anyhow::anyhow!("checklist item state is missing"))?;
            let updated = sqlx::query(
                r#"
                update checklist_items
                set
                  is_done = $3,
                  completed_at = case
                    when $3 then coalesce(completed_at, now())
                    else null
                  end,
                  updated_at = now()
                where id = $1 and checklist_id = $2 and deleted_at is null
                "#,
            )
            .bind(item_id)
            .bind(checklist_id)
            .bind(is_done)
            .execute(&mut **tx)
            .await?;
            if updated.rows_affected() != 1 {
                anyhow::bail!("checklist item does not belong to checklist");
            }
        }
    }
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
    if event.workspace_id != workspace_id.to_string()
        || event.entity_type != "card"
        || event.operation != "card.put"
    {
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
        let wins = current.is_none_or(|row| {
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

    let owner_user_id = sqlx::query_scalar::<_, Uuid>(
        "select owner_user_id from workspaces where id = $1",
    )
    .bind(workspace_id)
    .fetch_one(&mut *tx)
    .await?;
    let card_exists = sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from cards where id = $1)",
    )
    .bind(entity_id)
    .fetch_one(&mut *tx)
    .await?;
    if !card_exists {
        sqlx::query(
            r#"
            insert into cards (
              id, board_id, column_id, parent_card_id, title, description,
              status, priority, position, start_at, due_at, completed_at,
              created_by_user_id, archived_at
            ) values (
              $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::timestamptz,$11::timestamptz,
              $12::timestamptz,$13,case when $14 then now() else null end
            )
            "#,
        )
        .bind(entity_id)
        .bind(board_id)
        .bind(column_id)
        .bind(string_field(card, "parentCardId").map(Uuid::parse_str).transpose()?)
        .bind(string_field(card, "title").unwrap_or("Без названия"))
        .bind(string_field(card, "description"))
        .bind(string_field(card, "status").unwrap_or("active"))
        .bind(string_field(card, "priority"))
        .bind(card.get("position").and_then(Value::as_f64).unwrap_or(1_000.0))
        .bind(string_field(card, "startAt"))
        .bind(string_field(card, "dueAt"))
        .bind(string_field(card, "completedAt"))
        .bind(owner_user_id)
        .bind(card.get("isArchived").and_then(Value::as_bool).unwrap_or(false))
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
              status = case when $10 then $11 else status end,
              priority = case when $12 then $13 else priority end,
              position = case when $14 then $15 else position end,
              start_at = case when $16 then $17::timestamptz else start_at end,
              due_at = case when $18 then $19::timestamptz else due_at end,
              completed_at = case when $20 then $21::timestamptz else completed_at end,
              archived_at = case
                when $22 and $23 then coalesce(archived_at, now())
                when $22 then null
                else archived_at
              end,
              updated_at = now()
            where id = $1 and board_id = $24 and deleted_at is null
            "#,
        )
        .bind(entity_id)
        .bind(winning.contains("columnId"))
        .bind(column_id)
        .bind(winning.contains("parentCardId"))
        .bind(string_field(card, "parentCardId").map(Uuid::parse_str).transpose()?)
        .bind(winning.contains("title"))
        .bind(string_field(card, "title"))
        .bind(winning.contains("description"))
        .bind(string_field(card, "description"))
        .bind(winning.contains("status"))
        .bind(string_field(card, "status"))
        .bind(winning.contains("priority"))
        .bind(string_field(card, "priority"))
        .bind(winning.contains("position"))
        .bind(card.get("position").and_then(Value::as_f64))
        .bind(winning.contains("startAt"))
        .bind(string_field(card, "startAt"))
        .bind(winning.contains("dueAt"))
        .bind(string_field(card, "dueAt"))
        .bind(winning.contains("completedAt"))
        .bind(string_field(card, "completedAt"))
        .bind(winning.contains("isArchived"))
        .bind(card.get("isArchived").and_then(Value::as_bool).unwrap_or(false))
        .bind(board_id)
        .execute(&mut *tx)
        .await?;
    }

    if winning.contains("checklists") {
        if let Some(checklists) = event.payload.get("checklists") {
            apply_checklist_bundle(&mut tx, entity_id, checklists).await?;
        }
    }

    for field in winning {
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
        .bind(field)
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
