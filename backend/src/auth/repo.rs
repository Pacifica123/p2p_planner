use crate::error::{AppError, AppResult};

pub async fn ensure_auth_storage_ready() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth storage is wired but not implemented yet",
    ))
}
