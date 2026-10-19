# Contributing

The current engineering target is the reproducible offline pipeline described in `PROJECT_OUTLINE.md`. Please do not add browser capture or WebRTC dependencies before the offline quality baseline is measurable.

Before committing Rust changes, run:

```powershell
cargo fmt --all -- --check
cargo test --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

On Windows network shares, generated executables may be blocked. Point only the disposable build output to a local directory:

```powershell
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\Temp\reversewarp-target"
```

Never commit captured video, face crops, model weights, tokens, or generated reconstructions.
