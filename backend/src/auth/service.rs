use crate::error::{AppError, AppResult};

pub async fn sign_up() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_up is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_in() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_in is wired but business logic is not implemented yet",
    ))
}

pub async fn refresh() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.refresh is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_out() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_out is wired but business logic is not implemented yet",
    ))
}

pub async fn sign_out_all() -> AppResult<()> {
    Err(AppError::not_implemented(
        "auth.sign_out_all is wired but business logic is not implemented yet",
    ))
}
