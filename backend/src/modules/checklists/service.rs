use crate::error::AppResult;

pub async fn list_checklists() -> AppResult<()> {
    super::repo::list_checklists().await
}

pub async fn create_checklist() -> AppResult<()> {
    super::repo::create_checklist().await
}

pub async fn update_checklist() -> AppResult<()> {
    super::repo::update_checklist().await
}

pub async fn delete_checklist() -> AppResult<()> {
    super::repo::delete_checklist().await
}

pub async fn create_item() -> AppResult<()> {
    super::repo::create_item().await
}

pub async fn update_item() -> AppResult<()> {
    super::repo::update_item().await
}

pub async fn delete_item() -> AppResult<()> {
    super::repo::delete_item().await
}

