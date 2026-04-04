use crate::error::AppResult;

pub async fn get_current_user() -> AppResult<()> {
    super::repo::get_current_user().await
}

pub async fn list_devices() -> AppResult<()> {
    super::repo::list_devices().await
}

pub async fn revoke_device() -> AppResult<()> {
    super::repo::revoke_device().await
}

