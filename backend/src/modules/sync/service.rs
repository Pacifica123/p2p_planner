use crate::error::AppResult;

pub async fn get_status() -> AppResult<()> {
    super::repo::get_status().await
}

pub async fn list_replicas() -> AppResult<()> {
    super::repo::list_replicas().await
}

pub async fn register_replica() -> AppResult<()> {
    super::repo::register_replica().await
}

pub async fn push_changes() -> AppResult<()> {
    super::repo::push_changes().await
}

pub async fn pull_changes() -> AppResult<()> {
    super::repo::pull_changes().await
}

