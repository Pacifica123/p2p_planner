use crate::error::{AppError, AppResult};

pub async fn get_current_user() -> AppResult<()> {
    Err(AppError::not_implemented("users.get_current_user repo is wired but not implemented yet"))
}

pub async fn list_devices() -> AppResult<()> {
    Err(AppError::not_implemented("users.list_devices repo is wired but not implemented yet"))
}

pub async fn revoke_device() -> AppResult<()> {
    Err(AppError::not_implemented("users.revoke_device repo is wired but not implemented yet"))
}

