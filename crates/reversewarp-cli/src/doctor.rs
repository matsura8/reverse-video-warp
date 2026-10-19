use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};
use clap::Args;
use serde::Deserialize;

use crate::device::CudaDevice;

#[derive(Debug, Args)]
pub struct DoctorArgs {
    /// CUDA device to validate.
    #[arg(long, default_value = "cuda:0")]
    device: CudaDevice,

    /// Python executable from the CUDA worker environment.
    #[arg(long)]
    python: Option<PathBuf>,

    /// Worker entry point; defaults to inference-worker/worker.py.
    #[arg(long, default_value = "inference-worker/worker.py")]
    worker: PathBuf,
}

#[derive(Debug, Deserialize)]
struct Probe {
    cuda_available: bool,
    kind: String,
    name: String,
    resolved: String,
    torch_version: String,
    cuda_version: Option<String>,
    total_memory_bytes: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct SelfTest {
    deterministic: bool,
    identity_max_error: u8,
}

pub fn run(args: &DoctorArgs) -> Result<()> {
    verify_nvidia_smi(&args.device)?;
    let python = args.python.clone().unwrap_or_else(default_python);
    if !python.is_file() {
        bail!(
            "CUDA worker Python was not found at {}; run installer/windows/setup-cuda-worker.ps1",
            python.display()
        );
    }
    if !args.worker.is_file() {
        bail!(
            "worker entry point was not found: {}",
            args.worker.display()
        );
    }

    let probe: Probe = run_worker_json(&python, &args.worker, &args.device, "--probe")?;
    if !probe.cuda_available || probe.kind != "cuda" || probe.resolved != args.device.to_string() {
        bail!("worker did not resolve the requested CUDA device");
    }
    let self_test: SelfTest = run_worker_json(&python, &args.worker, &args.device, "--self-test")?;
    if !self_test.deterministic || self_test.identity_max_error != 0 {
        bail!("CUDA inverse-warp self-test failed quality requirements");
    }

    println!("ReverseWarp CUDA diagnostics: PASS");
    println!("  device: {} ({})", probe.resolved, probe.name);
    println!(
        "  memory: {} MiB",
        probe.total_memory_bytes.unwrap_or(0) / 1_048_576
    );
    println!("  PyTorch: {}", probe.torch_version);
    println!(
        "  CUDA runtime: {}",
        probe.cuda_version.as_deref().unwrap_or("unknown")
    );
    println!("  float32 inverse warp: deterministic, zero identity error");
    Ok(())
}

fn default_python() -> PathBuf {
    env::var_os("LOCALAPPDATA").map_or_else(
        || PathBuf::from("python"),
        |base| {
            PathBuf::from(base)
                .join("ReverseWarp")
                .join("venv")
                .join("Scripts")
                .join("python.exe")
        },
    )
}

fn verify_nvidia_smi(device: &CudaDevice) -> Result<()> {
    let output = Command::new("nvidia-smi.exe")
        .args(["--query-gpu=index,name", "--format=csv,noheader,nounits"])
        .output()
        .context("nvidia-smi.exe was not found or could not be started")?;
    if !output.status.success() {
        bail!(
            "nvidia-smi failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    let expected_prefix = format!("{},", device.index());
    if !String::from_utf8_lossy(&output.stdout)
        .lines()
        .any(|line| line.trim_start().starts_with(&expected_prefix))
    {
        bail!("{device} is not visible to nvidia-smi");
    }
    Ok(())
}

fn run_worker_json<T: for<'de> Deserialize<'de>>(
    python: &Path,
    worker: &Path,
    device: &CudaDevice,
    operation: &str,
) -> Result<T> {
    let output = Command::new(python)
        .arg(worker)
        .arg("--device")
        .arg(device.to_string())
        .arg(operation)
        .output()
        .with_context(|| format!("failed to start CUDA worker with {}", python.display()))?;
    if !output.status.success() {
        bail!(
            "CUDA worker {} failed: {}",
            operation,
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    serde_json::from_slice(&output.stdout)
        .with_context(|| format!("CUDA worker {operation} returned invalid JSON"))
}
