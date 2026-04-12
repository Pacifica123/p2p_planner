pub mod dto;
pub mod handler;
pub mod provider;
pub mod service;

use axum::{
    routing::{get, post},
    Router,
};

use crate::state::AppState;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/integrations/providers", get(handler::list_providers))
        .route(
            "/integrations/providers/{providerKey}",
            get(handler::get_provider_detail),
        )
        .route("/integrations/import-jobs", post(handler::create_import_job))
        .route("/integrations/export-jobs", post(handler::create_export_job))
        .route(
            "/integrations/webhooks/{providerKey}",
            post(handler::receive_webhook),
        )
}
