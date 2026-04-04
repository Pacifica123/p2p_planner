use uuid::Uuid;

use crate::{error::AppResult, state::AppState};

use super::dto::{ActivityListResponse, ListActivityQuery};

pub async fn list_board_activity(
    state: &AppState,
    actor_user_id: Uuid,
    board_id: Uuid,
    query: ListActivityQuery,
) -> AppResult<ActivityListResponse> {
    super::repo::list_board_activity(&state.db, actor_user_id, board_id, query).await
}

pub async fn list_card_activity(
    state: &AppState,
    actor_user_id: Uuid,
    card_id: Uuid,
    query: ListActivityQuery,
) -> AppResult<ActivityListResponse> {
    super::repo::list_card_activity(&state.db, actor_user_id, card_id, query).await
}
