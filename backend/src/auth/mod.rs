#[cfg(feature="nostr-shadow")]
pub mod device_link;
pub mod dto;
pub mod handler;
mod pairing;
pub mod repo;
pub mod service;
pub mod token;

use axum::{
    routing::{get, post},
    Router,
};

use crate::state::AppState;

pub fn router() -> Router<AppState> {
    let router=Router::new()
        .route("/auth/sign-up", post(handler::sign_up))
        .route("/auth/sign-in", post(handler::sign_in))
        .route("/auth/node-link/export", post(handler::export_node_link))
        .route("/auth/node-link/import", post(handler::import_node_link))
        .route("/auth/refresh", post(handler::refresh))
        .route("/auth/sign-out", post(handler::sign_out))
        .route("/auth/sign-out-all", post(handler::sign_out_all))
        .route("/auth/session", get(handler::get_session))
        .route("/auth/native/sign-up", post(handler::native_sign_up))
        .route("/auth/native/sign-in", post(handler::native_sign_in))
        .route("/auth/native/refresh", post(handler::native_refresh))
        .route("/auth/native/sign-out", post(handler::native_sign_out))
        .route("/auth/dev-bootstrap", post(handler::bootstrap_dev_user));
    #[cfg(feature="nostr-shadow")]
    let router=router.route("/auth/device-link/request",post(device_link::request))
    .route("/auth/device-link/prepare",post(device_link::prepare)).route("/auth/device-link/approve",post(device_link::approve))
    .route("/auth/device-link/accept",post(device_link::accept));
    router.layer(axum::extract::DefaultBodyLimit::max(16*1024*1024))
}
