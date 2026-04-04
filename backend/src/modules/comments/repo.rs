use crate::error::{AppError, AppResult};

pub async fn list_comments() -> AppResult<()> {
    Err(AppError::not_implemented("comments.list_comments repo is wired but not implemented yet"))
}

pub async fn create_comment() -> AppResult<()> {
    Err(AppError::not_implemented("comments.create_comment repo is wired but not implemented yet"))
}

pub async fn update_comment() -> AppResult<()> {
    Err(AppError::not_implemented("comments.update_comment repo is wired but not implemented yet"))
}

pub async fn delete_comment() -> AppResult<()> {
    Err(AppError::not_implemented("comments.delete_comment repo is wired but not implemented yet"))
}

