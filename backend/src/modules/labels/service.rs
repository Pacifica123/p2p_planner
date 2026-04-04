use crate::error::AppResult;

pub async fn list_labels() -> AppResult<()> {
    super::repo::list_labels().await
}

pub async fn create_label() -> AppResult<()> {
    super::repo::create_label().await
}

pub async fn update_label() -> AppResult<()> {
    super::repo::update_label().await
}

pub async fn delete_label() -> AppResult<()> {
    super::repo::delete_label().await
}

pub async fn replace_card_labels() -> AppResult<()> {
    super::repo::replace_card_labels().await
}

