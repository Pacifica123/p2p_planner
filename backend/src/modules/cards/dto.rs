use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ListCardsQuery {
    pub limit: Option<i64>,
    pub cursor: Option<String>,
    pub q: Option<String>,
    pub column_id: Option<String>,
    pub label_id: Option<String>,
    pub completed: Option<bool>,
    pub sort_by: Option<String>,
    pub sort_dir: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateCardRequest {
    pub title: String,
    pub description: Option<String>,
    pub column_id: Uuid,
    pub parent_card_id: Option<Uuid>,
    pub position: Option<f64>,
    pub status: Option<String>,
    pub priority: Option<String>,
    pub start_at: Option<String>,
    pub due_at: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateCardRequest {
    pub title: Option<String>,
    #[serde(default)]
    pub description: Option<Option<String>>,
    pub column_id: Option<Uuid>,
    #[serde(default)]
    pub parent_card_id: Option<Option<Uuid>>,
    pub status: Option<String>,
    pub priority: Option<String>,
    pub position: Option<f64>,
    #[serde(default)]
    pub start_at: Option<Option<String>>,
    #[serde(default)]
    pub due_at: Option<Option<String>>,
    #[serde(default)]
    pub completed_at: Option<Option<String>>,
    pub is_archived: Option<bool>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MoveCardRequest {
    pub target_column_id: Uuid,
    pub position: Option<f64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PageInfo {
    pub has_next_page: bool,
    pub next_cursor: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CardListResponse {
    pub items: Vec<CardResponse>,
    pub page_info: PageInfo,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct CardResponse {
    pub id: String,
    pub board_id: String,
    pub column_id: String,
    pub parent_card_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub status: Option<String>,
    pub priority: Option<String>,
    pub position: f64,
    pub start_at: Option<String>,
    pub due_at: Option<String>,
    pub completed_at: Option<String>,
    pub is_archived: bool,
    pub label_ids: Vec<String>,
    pub checklist_count: i64,
    pub checklist_completed_item_count: i64,
    pub comment_count: i64,
    pub created_by_user_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub archived_at: Option<String>,
}
