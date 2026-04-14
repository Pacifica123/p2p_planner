use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SignUpRequest {
    pub email: String,
    pub password: String,
    pub display_name: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SignInRequest {
    pub email: String,
    pub password: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DevBootstrapUserRequest {
    pub user_id: Option<String>,
    pub email: Option<String>,
    pub display_name: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DevBootstrapUserResponse {
    pub id: String,
    pub email: String,
    pub display_name: String,
    pub mode: &'static str,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct SessionUserResponse {
    pub id: String,
    pub email: String,
    pub display_name: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthSuccessResponse {
    pub authenticated: bool,
    pub mode: &'static str,
    pub access_token: String,
    pub access_token_expires_at: String,
    pub session_id: String,
    pub device_id: String,
    pub user: SessionUserResponse,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionResponse {
    pub authenticated: bool,
    pub mode: &'static str,
    pub session_id: Option<String>,
    pub device_id: Option<String>,
    pub user: Option<SessionUserResponse>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SignOutResponse {
    pub signed_out: bool,
    pub mode: &'static str,
}
