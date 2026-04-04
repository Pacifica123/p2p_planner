use std::time::Duration;

use axum::{
    BoxError, Router,
    error_handling::HandleErrorLayer,
    http::{HeaderName, Method, StatusCode, header},
    routing::get,
};
use tower::ServiceBuilder;
use tower::timeout::TimeoutLayer;
use tower_http::{
    cors::{Any, CorsLayer},
    limit::RequestBodyLimitLayer,
    trace::{DefaultMakeSpan, DefaultOnRequest, DefaultOnResponse, TraceLayer},
};

use crate::{http::router::{api_router, root_health}, state::AppState};

pub fn build_app(state: AppState) -> Router {
    let body_limit_bytes = state.settings.http.body_limit_mb * 1024 * 1024;

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PATCH,
            Method::PUT,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([
            header::AUTHORIZATION,
            header::CONTENT_TYPE,
            header::ACCEPT,
            HeaderName::from_static("x-user-id"),
        ]);

    let middleware = ServiceBuilder::new()
        .layer(RequestBodyLimitLayer::new(body_limit_bytes))
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().include_headers(false))
                .on_request(DefaultOnRequest::new().level(tracing::Level::INFO))
                .on_response(DefaultOnResponse::new().level(tracing::Level::INFO)),
        )
        .layer(cors)
        .layer(HandleErrorLayer::new(|_: BoxError| async {
            StatusCode::REQUEST_TIMEOUT
        }))
        .layer(TimeoutLayer::new(Duration::from_secs(30)));

    Router::new()
        .route("/health", get(root_health))
        .nest("/api/v1", api_router())
        .layer(middleware)
        .with_state(state)
}
