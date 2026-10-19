use std::env;
use std::fs::{self, File};
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use clap::Args;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::device::CudaDevice;

const LABEL: &str = "Estimated reconstruction";

#[derive(Debug, Args)]
pub struct ProcessArgs {
    /// Source video. `ReverseWarp` never modifies this file.
    pub input: PathBuf,
    /// Corrected video destination.
    #[arg(long)]
    pub output: PathBuf,
    /// Optional heatmap video destination.
    #[arg(long)]
    pub diagnostic: Option<PathBuf>,
    /// Optional split-screen comparison destination.
    #[arg(long)]
    pub comparison: Option<PathBuf>,
    /// CUDA inference device. CPU processing is intentionally rejected.
    #[arg(long, default_value = "cuda:0")]
    pub device: CudaDevice,
    /// Python executable from the installed CUDA worker environment.
    #[arg(long)]
    pub python: Option<PathBuf>,
    /// Offline worker entry point.
    #[arg(long, default_value = "inference-worker/offline.py")]
    pub worker: PathBuf,
    /// Pinned `FALdetector` checkout containing the validated weights.
    #[arg(long)]
    pub fal_root: Option<PathBuf>,
    /// Minimum manipulation probability required to apply correction.
    #[arg(long, default_value_t = 0.5)]
    pub threshold: f32,
    /// Run face detection and model inference every N frames.
    #[arg(long, default_value_t = 5)]
    pub detection_interval: u32,
    /// `FFmpeg` video encoder.
    #[arg(long, default_value = "h264_nvenc", value_parser = ["h264_nvenc", "libx264"])]
    pub encoder: String,
    /// Validate the job and print its plan without creating output files.
    #[arg(long)]
    pub dry_run: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct JobPlan {
    label: &'static str,
    input: PathBuf,
    output: PathBuf,
    diagnostic: Option<PathBuf>,
    comparison: Option<PathBuf>,
    provenance_manifest: PathBuf,
    device: String,
    source_immutable: bool,
    frames_persisted: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProcessingSummary {
    frames: u64,
    detected_frames: u64,
    corrected_frames: u64,
    bypass_frames: u64,
    tracking_lost_frames: u64,
    last_manipulation_probability: f64,
    audio_preserved: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProvenanceManifest<'a> {
    schema_version: u8,
    label: &'static str,
    created_unix_seconds: u64,
    source: Artifact,
    output: Artifact,
    diagnostic: Option<Artifact>,
    comparison: Option<Artifact>,
    device: String,
    fal_root: &'a Path,
    threshold: f32,
    detection_interval: u32,
    encoder: &'a str,
    summary: &'a ProcessingSummary,
    source_immutable: bool,
    frames_persisted: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Artifact {
    path: PathBuf,
    sha256: String,
    bytes: u64,
}

pub fn run(args: &ProcessArgs) -> Result<()> {
    let plan = validate(args)?;
    println!("{}", serde_json::to_string_pretty(&plan)?);
    if args.dry_run {
        return Ok(());
    }
    let python = args.python.clone().unwrap_or_else(default_python);
    let fal_root = args.fal_root.clone().unwrap_or_else(default_fal_root);
    if !python.is_file() {
        bail!("CUDA worker Python was not found: {}", python.display());
    }
    if !args.worker.is_file() {
        bail!("offline worker was not found: {}", args.worker.display());
    }
    if !fal_root.is_dir() {
        bail!("FALdetector checkout was not found: {}", fal_root.display());
    }

    let mut command = Command::new(&python);
    command
        .arg(&args.worker)
        .arg(&plan.input)
        .arg("--output")
        .arg(&plan.output)
        .arg("--fal-root")
        .arg(&fal_root)
        .arg("--device")
        .arg(args.device.to_string())
        .arg("--threshold")
        .arg(args.threshold.to_string())
        .arg("--detection-interval")
        .arg(args.detection_interval.to_string())
        .arg("--encoder")
        .arg(&args.encoder);
    if let Some(path) = &plan.diagnostic {
        command.arg("--diagnostic").arg(path);
    }
    if let Some(path) = &plan.comparison {
        command.arg("--comparison").arg(path);
    }
    let output = command
        .output()
        .context("failed to start offline CUDA worker")?;
    if !output.status.success() {
        bail!(
            "offline CUDA worker failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let summary: ProcessingSummary = serde_json::from_slice(&output.stdout)
        .context("offline CUDA worker returned invalid JSON")?;
    let manifest = ProvenanceManifest {
        schema_version: 1,
        label: LABEL,
        created_unix_seconds: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .context("system clock is before the Unix epoch")?
            .as_secs(),
        source: artifact(&plan.input)?,
        output: artifact(&plan.output)?,
        diagnostic: plan.diagnostic.as_deref().map(artifact).transpose()?,
        comparison: plan.comparison.as_deref().map(artifact).transpose()?,
        device: args.device.to_string(),
        fal_root: &fal_root,
        threshold: args.threshold,
        detection_interval: args.detection_interval,
        encoder: &args.encoder,
        summary: &summary,
        source_immutable: true,
        frames_persisted: false,
    };
    write_manifest(&plan.provenance_manifest, &manifest)?;
    println!("{}", serde_json::to_string_pretty(&summary)?);
    println!("provenance: {}", plan.provenance_manifest.display());
    Ok(())
}

fn validate(args: &ProcessArgs) -> Result<JobPlan> {
    if !(0.0..=1.0).contains(&args.threshold) {
        bail!("threshold must be between 0 and 1");
    }
    if args.detection_interval == 0 {
        bail!("detection interval must be positive");
    }
    let input = canonical_input(&args.input)?;
    let output = normalized_output(&args.output)?;
    let diagnostic = args
        .diagnostic
        .as_deref()
        .map(normalized_output)
        .transpose()?;
    let comparison = args
        .comparison
        .as_deref()
        .map(normalized_output)
        .transpose()?;

    ensure_distinct(&input, &output)?;
    if let Some(path) = &diagnostic {
        ensure_distinct(&input, path)?;
        ensure_distinct(&output, path)?;
    }
    if let Some(path) = &comparison {
        ensure_distinct(&input, path)?;
        ensure_distinct(&output, path)?;
        if let Some(diagnostic) = &diagnostic {
            ensure_distinct(diagnostic, path)?;
        }
    }
    let provenance_manifest = PathBuf::from(format!("{}.reversewarp.json", output.display()));
    ensure_available(&provenance_manifest)?;
    Ok(JobPlan {
        label: LABEL,
        input,
        output,
        diagnostic,
        comparison,
        provenance_manifest,
        device: args.device.to_string(),
        source_immutable: true,
        frames_persisted: false,
    })
}

fn default_python() -> PathBuf {
    local_app_data().join("ReverseWarp/venv/Scripts/python.exe")
}

fn default_fal_root() -> PathBuf {
    local_app_data().join("ReverseWarp/third_party/FALdetector")
}

fn local_app_data() -> PathBuf {
    env::var_os("LOCALAPPDATA").map_or_else(|| PathBuf::from("."), PathBuf::from)
}

fn artifact(path: &Path) -> Result<Artifact> {
    let file =
        File::open(path).with_context(|| format!("cannot hash artifact: {}", path.display()))?;
    let bytes = file.metadata()?.len();
    let mut reader = BufReader::new(file);
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(Artifact {
        path: path.to_path_buf(),
        sha256: format!("{:x}", digest.finalize()),
        bytes,
    })
}

fn write_manifest(path: &Path, manifest: &ProvenanceManifest<'_>) -> Result<()> {
    let temporary = path.with_extension("json.partial");
    let mut file = File::create(&temporary)
        .with_context(|| format!("cannot create manifest: {}", temporary.display()))?;
    serde_json::to_writer_pretty(&mut file, manifest)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    fs::rename(&temporary, path)
        .with_context(|| format!("cannot finalize manifest: {}", path.display()))
}

fn canonical_input(path: &Path) -> Result<PathBuf> {
    let metadata = fs::metadata(path)
        .with_context(|| format!("input does not exist or cannot be read: {}", path.display()))?;
    if !metadata.is_file() {
        bail!("input is not a file: {}", path.display());
    }
    fs::canonicalize(path).with_context(|| format!("cannot resolve input path: {}", path.display()))
}

fn normalized_output(path: &Path) -> Result<PathBuf> {
    if path.as_os_str().is_empty() {
        bail!("output path cannot be empty");
    }
    ensure_available(path)?;
    let parent = path
        .parent()
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let parent = fs::canonicalize(parent)
        .with_context(|| format!("output directory does not exist: {}", parent.display()))?;
    let name = path
        .file_name()
        .context("output path must include a file name")?;
    Ok(parent.join(name))
}

fn ensure_available(path: &Path) -> Result<()> {
    if path.exists() {
        bail!("refusing to overwrite existing path: {}", path.display());
    }
    Ok(())
}

fn ensure_distinct(left: &Path, right: &Path) -> Result<()> {
    if left == right {
        bail!(
            "input and output paths must all be distinct: {}",
            left.display()
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn args(input: PathBuf, output: PathBuf) -> ProcessArgs {
        ProcessArgs {
            input,
            output,
            diagnostic: None,
            comparison: None,
            device: "cuda:0".parse().unwrap(),
            python: None,
            worker: PathBuf::from("inference-worker/offline.py"),
            fal_root: None,
            threshold: 0.5,
            detection_interval: 5,
            encoder: "h264_nvenc".to_string(),
            dry_run: true,
        }
    }

    #[test]
    fn accepts_distinct_new_output() {
        let directory = tempdir().unwrap();
        let input = directory.path().join("input.mp4");
        fs::write(&input, b"fixture").unwrap();
        let plan = validate(&args(input, directory.path().join("output.mp4"))).unwrap();
        assert!(plan.source_immutable);
        assert!(!plan.frames_persisted);
        assert_eq!(plan.label, LABEL);
    }

    #[test]
    fn rejects_overwriting_source() {
        let directory = tempdir().unwrap();
        let input = directory.path().join("input.mp4");
        fs::write(&input, b"fixture").unwrap();
        let error = validate(&args(input.clone(), input)).unwrap_err();
        assert!(error.to_string().contains("overwrite"));
    }

    #[test]
    fn rejects_existing_destination() {
        let directory = tempdir().unwrap();
        let input = directory.path().join("input.mp4");
        let output = directory.path().join("output.mp4");
        fs::write(&input, b"fixture").unwrap();
        fs::write(&output, b"do not replace").unwrap();
        let error = validate(&args(input, output)).unwrap_err();
        assert!(error.to_string().contains("refusing to overwrite"));
    }
}
