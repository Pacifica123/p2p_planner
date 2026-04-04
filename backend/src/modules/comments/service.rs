use crate::error::AppResult;

pub async fn list_comments() -> AppResult<()> {
    super::repo::list_comments().await
}

pub async fn create_comment() -> AppResult<()> {
    super::repo::create_comment().await
}

pub async fn update_comment() -> AppResult<()> {
    super::repo::update_comment().await
}

pub async fn delete_comment() -> AppResult<()> {
    super::repo::delete_comment().await
}

