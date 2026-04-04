use uuid::Uuid;

use crate::{error::{AppError, AppResult}, state::AppState};

use super::dto::{
    CardListResponse, CardResponse, CreateCardRequest, ListCardsQuery, MoveCardRequest,
    UpdateCardRequest,
};

fn normalize_status(value: &str) -> Option<&'static str> {
    match value {
        "active" | "todo" | "in_progress" | "blocked" => Some("active"),
        "completed" | "done" => Some("completed"),
        "cancelled" => Some("cancelled"),
        _ => None,
    }
}

pub async fn list_cards(
    state: &AppState,
    actor_user_id: Uuid,
    board_id: Uuid,
    query: ListCardsQuery,
) -> AppResult<CardListResponse> {
    super::repo::list_cards(&state.db, actor_user_id, board_id, query).await
}

pub async fn create_card(
    state: &AppState,
    actor_user_id: Uuid,
    board_id: Uuid,
    mut payload: CreateCardRequest,
) -> AppResult<CardResponse> {
    if payload.title.trim().is_empty() {
        return Err(AppError::bad_request("Card title is required"));
    }
    if let Some(status) = payload.status.as_deref() {
        payload.status = Some(
            normalize_status(status)
                .ok_or_else(|| AppError::bad_request("Unsupported card status"))?
                .to_string(),
        );
    }
    if let Some(priority) = payload.priority.as_deref() {
        if !matches!(priority, "low" | "medium" | "high" | "urgent") {
            return Err(AppError::bad_request("Unsupported card priority"));
        }
    }

    super::repo::create_card(&state.db, actor_user_id, board_id, payload).await
}

pub async fn get_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
) -> AppResult<CardResponse> {
    super::repo::get_card(&state.db, actor_user_id, card_id).await
}

pub async fn update_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
    mut payload: UpdateCardRequest,
) -> AppResult<CardResponse> {
    if let Some(title) = &payload.title {
        if title.trim().is_empty() {
            return Err(AppError::bad_request("Card title cannot be empty"));
        }
    }
    if let Some(status) = payload.status.as_deref() {
        payload.status = Some(
            normalize_status(status)
                .ok_or_else(|| AppError::bad_request("Unsupported card status"))?
                .to_string(),
        );
    }
    if let Some(priority) = payload.priority.as_deref() {
        if !matches!(priority, "low" | "medium" | "high" | "urgent") {
            return Err(AppError::bad_request("Unsupported card priority"));
        }
    }

    super::repo::update_card(&state.db, actor_user_id, card_id, payload).await
}

pub async fn delete_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
) -> AppResult<CardResponse> {
    super::repo::delete_card(&state.db, actor_user_id, card_id).await
}

pub async fn move_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
    payload: MoveCardRequest,
) -> AppResult<CardResponse> {
    super::repo::move_card(&state.db, actor_user_id, card_id, payload).await
}

pub async fn archive_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
) -> AppResult<CardResponse> {
    super::repo::archive_card(&state.db, actor_user_id, card_id).await
}

pub async fn unarchive_card(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
) -> AppResult<CardResponse> {
    super::repo::unarchive_card(&state.db, actor_user_id, card_id).await
}
