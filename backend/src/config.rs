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

fn normalized_env(env: &str) -> String {
    env.trim().to_ascii_lowercase().replace('-', "_")
}

fn is_local_dev_env(env: &str) -> bool {
    matches!(
        normalized_env(env).as_str(),
        "local" | "dev" | "development" | "test" | "testing"
    )
}

fn is_hardened_env(env: &str) -> bool {
    matches!(
        normalized_env(env).as_str(),
        "beta" | "preview" | "staging" | "stage" | "self_host" | "selfhost" | "prod" | "production"
    )
}

fn looks_like_placeholder_secret(value: &str) -> bool {
    let normalized = value.trim().to_ascii_lowercase();
    normalized.is_empty()
        || normalized.contains("change-me")
        || normalized.contains("changeme")
        || normalized.contains("default")
        || normalized == "secret"
        || normalized == "dev-secret"
        || normalized == "local-secret"
}

impl Settings {
    pub fn load() -> Result<Self, ConfigError> {
        dotenvy::dotenv().ok();

        let settings: Self = Config::builder()
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
            .try_deserialize()?;

        settings.validate()?;
        Ok(settings)
    }

    fn validate(&self) -> Result<(), ConfigError> {
        let local_dev_env = is_local_dev_env(&self.app.env);
        let hardened_env = is_hardened_env(&self.app.env);

        if self.auth.enable_dev_header_auth && !local_dev_env {
            return Err(ConfigError::Message(
                "AUTH__ENABLE_DEV_HEADER_AUTH may only be enabled for local/dev/test profiles".to_string(),
            ));
        }

        if matches!(self.auth.cookie_same_site, CookieSameSite::None) && !self.auth.cookie_secure {
            return Err(ConfigError::Message(
                "AUTH__COOKIE_SAME_SITE=none requires AUTH__COOKIE_SECURE=true".to_string(),
            ));
        }

        if hardened_env {
            if self.http.cors_allowed_origins.is_empty() {
                return Err(ConfigError::Message(
                    "HTTP__CORS_ALLOWED_ORIGINS must be explicit for beta/self-host/production profiles".to_string(),
                ));
            }

            if self
                .http
                .cors_allowed_origins
                .iter()
                .any(|origin| origin.trim() == "*")
            {
                return Err(ConfigError::Message(
                    "HTTP__CORS_ALLOWED_ORIGINS must not contain wildcard '*' for beta/self-host/production profiles".to_string(),
                ));
            }

            if !self.auth.cookie_secure {
                return Err(ConfigError::Message(
                    "AUTH__COOKIE_SECURE=true is required for beta/self-host/production profiles".to_string(),
                ));
            }

            if looks_like_placeholder_secret(&self.auth.jwt_secret) || self.auth.jwt_secret.len() < 32 {
                return Err(ConfigError::Message(
                    "AUTH__JWT_SECRET must be a non-default secret with at least 32 characters for beta/self-host/production profiles".to_string(),
                ));
            }
        }

        Ok(())
    }

    pub fn dev_header_auth_allowed(&self) -> bool {
        self.auth.enable_dev_header_auth && is_local_dev_env(&self.app.env)
    }

    pub fn socket_addr(&self) -> SocketAddr {
        SocketAddr::new(self.app.host, self.app.port)
    }
}
