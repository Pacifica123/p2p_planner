use serde::Serialize;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChecklistResponse { pub id: String, pub card_id: String, pub title: String }

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChecklistItemResponse { pub id: String, pub checklist_id: String, pub title: String, pub is_done: bool }
