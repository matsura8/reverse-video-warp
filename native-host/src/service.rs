use std::sync::{Arc, Mutex};

use axum::body::Bytes;
use axum::extract::{DefaultBodyLimit, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Serialize;

use crate::session::SessionStore;
use crate::worker::Worker;

#[derive(Clone)]
pub struct AppState {
    pub sessions: Arc<SessionStore>,
    pub worker: Arc<Mutex<Worker>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Health {
    status: &'static str,
    service: &'static str,
    transport: &'static str,
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/v1/frame", post(process_frame))
        .layer(DefaultBodyLimit::max(8_000_000))
        .with_state(state)
}

async fn health() -> Json<Health> {
    Json(Health {
        status: "ok",
        service: "ReverseWarp Local",
        transport: "binary-jpeg",
    })
}

async fn process_frame(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    let token = headers
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "));
    let origin = headers
        .get(header::ORIGIN)
        .and_then(|value| value.to_str().ok());
    if !token.is_some_and(|value| state.sessions.validate(value, origin)) {
        return (StatusCode::UNAUTHORIZED, "invalid or expired session").into_response();
    }
    if headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        != Some("image/jpeg")
    {
        return (StatusCode::UNSUPPORTED_MEDIA_TYPE, "expected image/jpeg").into_response();
    }
    let worker = Arc::clone(&state.worker);
    match tokio::task::spawn_blocking(move || {
        worker.lock().expect("worker mutex poisoned").process(&body)
    })
    .await
    {
        Ok(Ok((jpeg, metrics))) => {
            let mut response = (StatusCode::OK, jpeg).into_response();
            response.headers_mut().insert(
                header::CONTENT_TYPE,
                header::HeaderValue::from_static("image/jpeg"),
            );
            if let Some(value) = metrics.applied {
                response.headers_mut().insert(
                    "x-reversewarp-applied",
                    header::HeaderValue::from_static(if value { "true" } else { "false" }),
                );
            }
            if let Some(value) = metrics.face_detected {
                response.headers_mut().insert(
                    "x-reversewarp-face-detected",
                    header::HeaderValue::from_static(if value { "true" } else { "false" }),
                );
            }
            if let Some(value) = metrics
                .manipulation_probability
                .and_then(|value| header::HeaderValue::from_str(&value.to_string()).ok())
            {
                response
                    .headers_mut()
                    .insert("x-reversewarp-probability", value);
            }
            response
        }
        Ok(Err(error)) => (StatusCode::BAD_GATEWAY, error.to_string()).into_response(),
        Err(error) => (StatusCode::INTERNAL_SERVER_ERROR, error.to_string()).into_response(),
    }
}
