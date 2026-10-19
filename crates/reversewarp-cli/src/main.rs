mod device;
mod doctor;
mod process;

use anyhow::Result;
use clap::{Parser, Subcommand};
use process::ProcessArgs;

#[derive(Debug, Parser)]
#[command(name = "reversewarp", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Verify NVIDIA, `PyTorch` CUDA, and the inverse-warp kernel.
    Doctor(doctor::DoctorArgs),
    /// Validate and prepare one local video processing job.
    Process(ProcessArgs),
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Doctor(args) => doctor::run(&args),
        Command::Process(args) => process::run(&args),
    }
}
