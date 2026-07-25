pub(crate) mod repo;
mod worker;

use std::sync::Arc;

use sqlx::PgPool;

use crate::config::Settings;

pub use repo::transport_queue_status;

pub fn spawn_workers(settings: Arc<Settings>, db: PgPool) {
    worker::spawn_nostr_worker(settings, db);
}
