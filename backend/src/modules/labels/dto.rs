use serde::Serialize;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LabelResponse { pub id: String, pub board_id: String, pub name: String, pub color: String }
