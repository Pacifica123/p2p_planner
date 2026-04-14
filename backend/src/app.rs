use std::time::Duration;

use axum::{
    BoxError, Router,
    error_handling::HandleErrorLayer,
    http::{HeaderValue, Method, StatusCode, header},
    middleware,
    routing::get,
};
use tower::ServiceBuilder;
use tower::timeout::TimeoutLayer;
use tower_http::{
    cors::{AllowOrigin, CorsLayer},
    limit::RequestBodyLimitLayer,
    trace::{DefaultMakeSpan, DefaultOnRequest, DefaultOnResponse, TraceLayer},
};

use crate::{
    http::{
        middleware::rate_limit_middleware,
        router::{api_router, root_health},
    },
    state::AppState,
};

pub fn build_app(state: AppState) -> Router {
    let body_limit_bytes = state.settings.http.body_limit_mb * 1024 * 1024;

    let allowed_origins = state
        .settings
        .http
        .cors_allowed_origins
        .iter()
        .filter_map(|value| HeaderValue::from_str(value).ok())
        .collect::<Vec<_>>();

    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list(allowed_origins))
        .allow_credentials(true)
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
        ]);

    let middleware_stack = ServiceBuilder::new()
        .layer(RequestBodyLimitLayer::new(body_limit_bytes))
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().include_headers(false))
                .on_request(DefaultOnRequest::new().level(tracing::Level::INFO))
                .on_response(DefaultOnResponse::new().level(tracing::Level::INFO)),
        )
        .layer(cors)
        .layer(HandleErrorLayer::new(|_: BoxError| async { StatusCode::REQUEST_TIMEOUT }))
        .layer(TimeoutLayer::new(Duration::from_secs(30)));

    Router::new()
        .route("/health", get(root_health))
        .nest("/api/v1", api_router())
        .layer(middleware::from_fn_with_state(state.clone(), rate_limit_middleware))
        .layer(middleware_stack)
        .with_state(state)
}
