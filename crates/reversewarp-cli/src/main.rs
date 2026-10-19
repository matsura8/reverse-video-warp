use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "reversewarp", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Process one local video without modifying the source.
    Process,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Command::Process => {
            anyhow::bail!("the offline processing pipeline has not been enabled yet")
        }
    }
}
