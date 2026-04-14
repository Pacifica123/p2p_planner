use std::net::{IpAddr, SocketAddr};

use config::{Config, ConfigError, Environment, File};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct Settings {
    pub app: AppSettings,
    pub database: DatabaseSettings,
    pub http: HttpSettings,
    pub auth: AuthSettings,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AppSettings {
    pub name: String,
    pub env: String,
    pub host: IpAddr,
    pub port: u16,
    pub log_format: LogFormat,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DatabaseSettings {
    pub url: String,
    pub max_connections: u32,
    pub min_connections: u32,
    pub connect_timeout_secs: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HttpSettings {
    pub body_limit_mb: usize,
    pub cors_allowed_origins: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AuthSettings {
    pub jwt_secret: String,
    #[serde(default)]
    pub previous_jwt_secrets: Vec<String>,
    pub access_token_ttl_minutes: i64,
    pub refresh_token_ttl_days: i64,
    pub public_signup_enabled: bool,
    #[serde(default = "default_refresh_cookie_name")]
    pub refresh_cookie_name: String,
    #[serde(default = "default_device_cookie_name")]
    pub device_cookie_name: String,
    #[serde(default = "default_cookie_same_site")]
    pub cookie_same_site: CookieSameSite,
    #[serde(default)]
    pub cookie_secure: bool,
    #[serde(default)]
    pub enable_dev_header_auth: bool,
    #[serde(default = "default_auth_rate_limit_window_secs")]
    pub auth_rate_limit_window_secs: u64,
    #[serde(default = "default_auth_rate_limit_max_attempts")]
    pub auth_rate_limit_max_attempts: u32,
    #[serde(default = "default_sensitive_rate_limit_window_secs")]
    pub sensitive_rate_limit_window_secs: u64,
    #[serde(default = "default_sensitive_rate_limit_max_attempts")]
    pub sensitive_rate_limit_max_attempts: u32,
}

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    Pretty,
    Json,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CookieSameSite {
    Lax,
    Strict,
    None,
}

fn default_refresh_cookie_name() -> String {
    "p2p_planner_refresh".to_string()
}

fn default_device_cookie_name() -> String {
    "p2p_planner_device".to_string()
}

fn default_cookie_same_site() -> CookieSameSite {
    CookieSameSite::Lax
}

fn default_auth_rate_limit_window_secs() -> u64 {
    60
}

fn default_auth_rate_limit_max_attempts() -> u32 {
    20
}

fn default_sensitive_rate_limit_window_secs() -> u64 {
    60
}

fn default_sensitive_rate_limit_max_attempts() -> u32 {
    60
}

impl CookieSameSite {
    pub fn as_set_cookie_value(self) -> &'static str {
        match self {
            Self::Lax => "Lax",
            Self::Strict => "Strict",
            Self::None => "None",
        }
    }
}

impl Settings {
    pub fn load() -> Result<Self, ConfigError> {
        dotenvy::dotenv().ok();

        Config::builder()
            .add_source(File::with_name("config/default").required(false))
            .add_source(
                Environment::default()
                    .separator("__")
                    .list_separator(",")
                    .with_list_parse_key("http.cors_allowed_origins")
                    .with_list_parse_key("auth.previous_jwt_secrets")
                    .try_parsing(true),
            )
            .build()?
            .try_deserialize()
    }

    pub fn socket_addr(&self) -> SocketAddr {
        SocketAddr::new(self.app.host, self.app.port)
    }
}
