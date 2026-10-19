# ReverseWarp Local

ReverseWarp Local is a local-first research project for estimating and visualizing inverse facial warps in video. The result is always presented as an **Estimated reconstruction**; it is not an authentic recovery of removed pixels or proof of manipulation.

The repository currently targets the first engineering milestone: a safe, offline Rust command-line demonstrator. Browser capture and live WebRTC work begin only after the offline pipeline has a repeatable quality baseline.

## Status

Early scaffold. No FAL model or production video pipeline is included yet.

## Build

```powershell
cargo build --workspace
cargo test --workspace
```

## Planned command

```powershell
reversewarp process input.mp4 `
  --output corrected.mp4 `
  --diagnostic heatmap.mp4 `
  --comparison split.mp4 `
  --device cuda:0
```

See [PROJECT_OUTLINE.md](PROJECT_OUTLINE.md) for scope, safety constraints, architecture, and delivery phases.

## Safety boundary

- Local processing only; no telemetry or cloud APIs.
- Source files remain immutable.
- Protected-media restrictions are not bypassed.
- Generated outputs must carry an `Estimated reconstruction` provenance sidecar.
- Browser and model inputs are untrusted and must be validated.

