use crate::error::{AppError, AppResult};

pub async fn get_status() -> AppResult<()> {
    Err(AppError::not_implemented("sync.get_status repo is wired but not implemented yet"))
}

pub async fn list_replicas() -> AppResult<()> {
    Err(AppError::not_implemented("sync.list_replicas repo is wired but not implemented yet"))
}

pub async fn register_replica() -> AppResult<()> {
    Err(AppError::not_implemented("sync.register_replica repo is wired but not implemented yet"))
}

pub async fn push_changes() -> AppResult<()> {
    Err(AppError::not_implemented("sync.push_changes repo is wired but not implemented yet"))
}

pub async fn pull_changes() -> AppResult<()> {
    Err(AppError::not_implemented("sync.pull_changes repo is wired but not implemented yet"))
}

