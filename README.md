# ReverseWarp Local

ReverseWarp Local is a local-first research project for estimating and visualizing inverse facial warps in video. The result is always presented as an **Estimated reconstruction**; it is not an authentic recovery of removed pixels or proof of manipulation.

The repository now includes a safe, offline Rust command-line demonstrator backed by the pinned `FALdetector` models and a CUDA-first video pipeline. Browser capture and live WebRTC remain under active development.

## Status

Offline and browser MVP milestones are complete. The CLI supervises local CUDA inference, tracks faces, applies temporally smoothed inverse warps, encodes through NVENC, preserves source audio, emits heatmap and split-screen views, and writes a SHA-256 provenance manifest. The browser packages capture a selected video, proxy frames through an origin-bound Rust loopback host and persistent CUDA worker, and embed a processed video overlay while keeping the original available for fail-open. Model weights are installed locally and are intentionally not committed.

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

## Install the browser runtime

```powershell
.\installer\windows\install.ps1
```

The user-scope installer builds release binaries, packages Chromium and Firefox extensions, installs the bounded Python worker sources, and registers the native host for Edge, Chrome, and Firefox. It does not silently add an unpacked extension to a browser profile. Load the matching package once from:

- Edge or Chrome: `%LOCALAPPDATA%\ReverseWarp\extensions\chromium`
- Firefox temporary/development install: `%LOCALAPPDATA%\ReverseWarp\extensions\firefox\manifest.json`

On an ordinary non-protected HTML5 video, click the ReverseWarp toolbar action (or press `Ctrl+Shift+Y`). The extension chooses the largest playing video, captures it directly when allowed, uses Edge/Chrome tab capture or Firefox's explicit display picker as a fallback, and places a muted generated video stream over the source. Source audio continues locally. The always-visible control reports `corrected` or `bypass`; clicking it stops capture and immediately reveals the original.

The live browser transport is bounded binary JPEG over `127.0.0.1:17842`, authenticated with an origin-bound 256-bit session token. Native Messaging carries control messages only. No frames are saved by the live path.

To remove the installation and browser registrations:

```powershell
.\installer\windows\uninstall.ps1
```

## Verification

```powershell
$env:CARGO_TARGET_DIR = "$env:LOCALAPPDATA\Temp\reversewarp-target"
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
npm test --prefix extension
$env:PYTHONPATH = (Resolve-Path inference-worker).Path
& "$env:LOCALAPPDATA\ReverseWarp\venv\Scripts\python.exe" -m unittest discover -s inference-worker/tests -v
```

The optional Edge acceptance runner requires Selenium in a disposable test environment and the fixture server described in [tests/integration/README.md](tests/integration/README.md). It asserts that the original video remains present, a processed video is embedded, the provenance label is visible, and Stop reveals the original.

See [PROJECT_OUTLINE.md](PROJECT_OUTLINE.md) for scope, safety constraints, architecture, and delivery phases.

## Safety boundary

- Local processing only; no telemetry or cloud APIs.
- Source files remain immutable.
- Protected-media restrictions are not bypassed.
- Generated outputs must carry an `Estimated reconstruction` provenance sidecar.
- Browser and model inputs are untrusted and must be validated.

