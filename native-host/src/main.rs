mod native_messaging;
mod service;
mod session;
mod worker;

use std::env;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result};
use service::AppState;
use session::SessionStore;
use worker::Worker;

const DEFAULT_PORT: u16 = 17_842;

#[tokio::main]
async fn main() -> Result<()> {
    let python = env_path("LOCALAPPDATA", "ReverseWarp/venv/Scripts/python.exe")?;
    let fal_root = env_path("LOCALAPPDATA", "ReverseWarp/third_party/FALdetector")?;
    let worker_entry = env::current_dir()?.join("inference-worker/live.py");
    let threshold = env::var("REVERSEWARP_THRESHOLD")
        .ok()
        .map(|value| value.parse::<f32>())
        .transpose()
        .context("REVERSEWARP_THRESHOLD must be a number between 0 and 1")?
        .unwrap_or(0.5);
    if !(0.0..=1.0).contains(&threshold) {
        anyhow::bail!("REVERSEWARP_THRESHOLD must be between 0 and 1");
    }
    let worker = Worker::start(&python, &worker_entry, &fal_root, "cuda:0", threshold)?;
    let state = AppState {
        sessions: Arc::new(SessionStore::default()),
        worker: Arc::new(Mutex::new(worker)),
    };
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", DEFAULT_PORT))
        .await
        .with_context(|| format!("cannot bind ReverseWarp loopback port {DEFAULT_PORT}"))?;
    let server_state = state.clone();
    tokio::spawn(async move {
        if let Err(error) = axum::serve(listener, service::router(server_state)).await {
            eprintln!("ReverseWarp localhost service stopped: {error}");
        }
    });

    let origin = env::args()
        .nth(1)
        .unwrap_or_else(|| "reversewarp-development".to_string());
    tokio::task::spawn_blocking(move || native_messaging::serve(&state, &origin, DEFAULT_PORT))
        .await??;
    Ok(())
}

fn env_path(variable: &str, suffix: &str) -> Result<PathBuf> {
    let base = env::var_os(variable).with_context(|| format!("{variable} is not set"))?;
    Ok(PathBuf::from(base).join(suffix))
}
