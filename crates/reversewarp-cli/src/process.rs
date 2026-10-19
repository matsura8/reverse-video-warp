use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use clap::Args;
use serde::Serialize;

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
    /// Inference device, such as cuda:0 or cpu.
    #[arg(long, default_value = "cuda:0")]
    pub device: String,
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

pub fn run(args: &ProcessArgs) -> Result<()> {
    let plan = validate(args)?;
    println!("{}", serde_json::to_string_pretty(&plan)?);
    if args.dry_run {
        return Ok(());
    }
    bail!(
        "processing is not enabled yet; rerun with --dry-run to validate the job without writing files"
    )
}

fn validate(args: &ProcessArgs) -> Result<JobPlan> {
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
    if args.device.trim().is_empty() {
        bail!("device cannot be empty");
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
        device: args.device.clone(),
        source_immutable: true,
        frames_persisted: false,
    })
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
            device: "cuda:0".to_owned(),
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
