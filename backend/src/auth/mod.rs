pub mod dto;
pub mod handler;
pub mod repo;
pub mod service;
pub mod token;

use axum::{routing::{get, post}, Router};

use crate::state::AppState;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/auth/sign-up", post(handler::sign_up))
        .route("/auth/sign-in", post(handler::sign_in))
        .route("/auth/refresh", post(handler::refresh))
        .route("/auth/sign-out", post(handler::sign_out))
        .route("/auth/sign-out-all", post(handler::sign_out_all))
        .route("/auth/session", get(handler::get_session))
}
