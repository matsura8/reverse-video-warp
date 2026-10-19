# ReverseWarp Local

ReverseWarp Local is a local-first research project for estimating and visualizing inverse facial warps in video. The result is always presented as an **Estimated reconstruction**; it is not an authentic recovery of removed pixels or proof of manipulation.

The repository now includes a safe, offline Rust command-line demonstrator backed by the pinned `FALdetector` models and a CUDA-first video pipeline. Browser capture and live WebRTC remain under active development.

## Status

Offline milestone complete: the CLI supervises local CUDA inference, tracks faces, applies temporally smoothed inverse warps, encodes through NVENC, preserves source audio, emits heatmap and split-screen views, and writes a SHA-256 provenance manifest. Model weights are installed locally and are intentionally not committed.

## Build

```powershell
cargo build --workspace
cargo test --workspace
```

## CUDA setup and diagnostics

The production path requires an NVIDIA CUDA device. CPU execution is not accepted by the Rust CLI.

```powershell
.\installer\windows\setup-cuda-worker.ps1
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\Temp\reversewarp-target"
cargo run --bin reversewarp -- doctor --device cuda:0
```

`doctor` verifies that the requested GPU is visible through `nvidia-smi`, that PyTorch loaded a CUDA build, and that a deterministic float32 inverse warp completes with zero identity error.

## Process a local video

```powershell
reversewarp process input.mp4 `
  --output corrected.mp4 `
  --diagnostic heatmap.mp4 `
  --comparison split.mp4 `
  --device cuda:0
```

The source is never overwritten. Existing destinations are rejected, and each successful job writes `corrected.mp4.reversewarp.json` with artifact hashes, CUDA/model settings, processing counts, and the required `Estimated reconstruction` label.

See [PROJECT_OUTLINE.md](PROJECT_OUTLINE.md) for scope, safety constraints, architecture, and delivery phases.

## Safety boundary

- Local processing only; no telemetry or cloud APIs.
- Source files remain immutable.
- Protected-media restrictions are not bypassed.
- Generated outputs must carry an `Estimated reconstruction` provenance sidecar.
- Browser and model inputs are untrusted and must be validated.

