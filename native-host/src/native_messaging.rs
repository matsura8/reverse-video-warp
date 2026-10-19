use std::io::{self, Read, Write};

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};

use crate::service::AppState;

const MAX_MESSAGE_BYTES: usize = 64 * 1024;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase", deny_unknown_fields)]
enum Request {
    Health,
    StartSession,
    StopSession { token: String },
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Response<'a> {
    ok: bool,
    status: &'a str,
    token: Option<String>,
    endpoint: Option<String>,
}

pub fn serve(state: &AppState, origin: &str, port: u16) -> Result<()> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut input = stdin.lock();
    let mut output = stdout.lock();
    loop {
        let Some(payload) = read_message(&mut input)? else {
            return Ok(());
        };
        let request: Request =
            serde_json::from_slice(&payload).context("invalid native message")?;
        let response = match request {
            Request::Health => Response {
                ok: true,
                status: "ready",
                token: None,
                endpoint: Some(format!("http://127.0.0.1:{port}")),
            },
            Request::StartSession => Response {
                ok: true,
                status: "live",
                token: Some(state.sessions.create(origin)),
                endpoint: Some(format!("http://127.0.0.1:{port}")),
            },
            Request::StopSession { token } => Response {
                ok: state.sessions.revoke(&token),
                status: "stopped",
                token: None,
                endpoint: None,
            },
        };
        write_message(&mut output, &response)?;
    }
}

fn read_message(reader: &mut impl Read) -> Result<Option<Vec<u8>>> {
    let mut length = [0_u8; 4];
    match reader.read_exact(&mut length) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
        Err(error) => return Err(error.into()),
    }
    let length = u32::from_le_bytes(length) as usize;
    if length == 0 || length > MAX_MESSAGE_BYTES {
        bail!("native message length is invalid");
    }
    let mut payload = vec![0_u8; length];
    reader.read_exact(&mut payload)?;
    Ok(Some(payload))
}

fn write_message(writer: &mut impl Write, value: &impl Serialize) -> Result<()> {
    let payload = serde_json::to_vec(value)?;
    let length = u32::try_from(payload.len()).context("native response is too large")?;
    writer.write_all(&length.to_le_bytes())?;
    writer.write_all(&payload)?;
    writer.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_oversized_native_message() {
        let length = u32::try_from(MAX_MESSAGE_BYTES + 1).unwrap().to_le_bytes();
        let error = read_message(&mut length.as_slice()).unwrap_err();
        assert!(error.to_string().contains("length"));
    }
}
