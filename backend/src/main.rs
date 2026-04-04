use anyhow::Context;
use sqlx::migrate::Migrator;

use p2p_planner_backend::{
    app::build_app,
    config::Settings,
    db::pool::create_pool,
    state::AppState,
    telemetry::init_tracing,
};

static MIGRATOR: Migrator = sqlx::migrate!();

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let settings = Settings::load().context("failed to load settings")?;
    init_tracing(settings.app.log_format);

    let addr = settings.socket_addr();
    let db = create_pool(&settings.database)
        .await
        .context("failed to connect to postgres")?;

    MIGRATOR
        .run(&db)
        .await
        .context("failed to run database migrations")?;

    let state = AppState::new(settings, db);
    let app = build_app(state);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .context("failed to bind tcp listener")?;

    tracing::info!(%addr, "starting HTTP server");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .context("server error")?;

    Ok(())
}

async fn shutdown_signal() {
    tokio::signal::ctrl_c()
        .await
        .expect("failed to install Ctrl+C handler");

    tracing::info!("shutdown signal received");
}
