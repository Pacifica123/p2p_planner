use axum::{extract::State, routing::get, Router};

use crate::{
    auth,
    http::response::{ok, ApiEnvelope, HealthPayload},
    modules::{activity, appearance, audit, boards, cards, checklists, comments, labels, sync, users, workspaces},
    state::AppState,
};

pub fn api_router() -> Router<AppState> {
    Router::new()
        .route("/health", get(api_health))
        .merge(auth::router())
        .merge(users::router())
        .merge(appearance::router())
        .merge(activity::router())
        .merge(workspaces::router())
        .merge(boards::router())
        .merge(cards::router())
        .merge(labels::router())
        .merge(checklists::router())
        .merge(comments::router())
        .merge(sync::router())
        .merge(audit::router())
}

pub async fn root_health(State(state): State<AppState>) -> axum::Json<ApiEnvelope<HealthPayload>> {
    ok(HealthPayload {
        status: "ok",
        service: state.settings.app.name.clone(),
        version: env!("CARGO_PKG_VERSION"),
        env: state.settings.app.env.clone(),
    })
}

async fn api_health(State(state): State<AppState>) -> axum::Json<ApiEnvelope<HealthPayload>> {
    ok(HealthPayload {
        status: "ok",
        service: state.settings.app.name.clone(),
        version: env!("CARGO_PKG_VERSION"),
        env: state.settings.app.env.clone(),
    })
}
