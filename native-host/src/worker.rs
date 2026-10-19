use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

use anyhow::{Context, Result, bail};
use base64::Engine;
use serde::{Deserialize, Serialize};

#[derive(Debug)]
pub struct Worker {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

#[derive(Debug, Serialize)]
struct FrameRequest<'a> {
    frame: &'a str,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FrameResponse {
    pub ok: bool,
    pub frame: Option<String>,
    pub error: Option<String>,
    pub applied: Option<bool>,
    pub face_detected: Option<bool>,
    pub manipulation_probability: Option<f64>,
}

impl Worker {
    pub fn start(
        python: &Path,
        entry: &Path,
        fal_root: &Path,
        device: &str,
        threshold: f32,
    ) -> Result<Self> {
        let mut child = Command::new(python)
            .arg(entry)
            .arg("--fal-root")
            .arg(fal_root)
            .arg("--device")
            .arg(device)
            .arg("--threshold")
            .arg(threshold.to_string())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .context("failed to start persistent CUDA worker")?;
        let stdin = child.stdin.take().context("worker stdin is unavailable")?;
        let stdout = child
            .stdout
            .take()
            .context("worker stdout is unavailable")?;
        let mut worker = Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        };
        let ready: serde_json::Value = worker.read_json()?;
        if ready.get("ready") != Some(&serde_json::Value::Bool(true)) {
            bail!("CUDA worker did not report ready");
        }
        Ok(worker)
    }

    pub fn process(&mut self, jpeg: &[u8]) -> Result<(Vec<u8>, FrameResponse)> {
        if jpeg.len() > 8_000_000 {
            bail!("frame exceeds 8 MB limit");
        }
        let encoded = base64::engine::general_purpose::STANDARD.encode(jpeg);
        serde_json::to_writer(&mut self.stdin, &FrameRequest { frame: &encoded })?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
        let response: FrameResponse = self.read_json()?;
        if !response.ok {
            bail!(
                "CUDA worker rejected frame: {}",
                response.error.as_deref().unwrap_or("unknown error")
            );
        }
        let payload = response
            .frame
            .as_deref()
            .context("worker response omitted frame")?;
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(payload)
            .context("worker returned invalid base64")?;
        Ok((decoded, response))
    }

    fn read_json<T: for<'de> Deserialize<'de>>(&mut self) -> Result<T> {
        let mut line = String::new();
        if self.stdout.read_line(&mut line)? == 0 {
            let status = self.child.try_wait()?;
            bail!("CUDA worker closed its output (status: {status:?})");
        }
        serde_json::from_str(&line).context("CUDA worker returned invalid JSON")
    }
}
