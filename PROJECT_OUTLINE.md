# ReverseWarp Local

## 1. Objective

Build local-first Firefox, Chrome, and Edge extensions plus a shared GPU service that:

1. Captures video displayed in the active browser tab after an explicit user action.
2. Detects and tracks faces locally.
3. Uses FALdetector to estimate Face-Aware Liquify-style facial deformation.
4. Applies a temporally stabilized inverse warp.
5. Returns the processed stream to an overlay positioned over the original browser video.
6. Preserves the original audio and allows instant comparison or bypass.

The displayed result must be labeled **Estimated reconstruction**. It is not an authentic recovery of removed pixels or proof that an image was manipulated.

## 2. Initial scope

### Supported in the MVP

- Chrome and Edge on Windows using a shared Chromium Manifest V3 build.
- Firefox on Windows using a Firefox-specific Manifest V3 build and background-document adapter.
- User-initiated capture of the active tab.
- One visible 720p or 1080p video with one primarily frontal face.
- Local processing on the same computer as the browser.
- RTX 4080 as the primary GPU.
- H.264 input and browser-compatible WebRTC output.
- Original, corrected, heatmap, and split-screen views.
- Live preview and offline file-processing modes.

### Explicitly out of scope for the MVP

- Bypassing DRM, protected-media paths, site access controls, or capture restrictions.
- Claiming that the reconstructed face is the historical original.
- Arbitrary deepfake reversal, face-swap reversal, generative-fill reversal, or de-airbrushing.
- Safari support.
- Remote/cloud processing.
- Multiple simultaneous tabs or multiple high-resolution faces.

## 3. System architecture

```text
Browser extension
  action button
      |
      +-- service worker ---------------- Native Messaging ----------------+
      |          control, health, port and one-time session token           |
      |                                                                      v
      +-- capture adapter ============ WebRTC input =====> Rust local service
      |                                                capture/session control
      |                                                         |
      |                                                         v
      |                                               decode and frame pipeline
      |                                                         |
      |                                                         v
      |                                               Python FAL worker process
      |                                                         |
      |                                                         v
      +-- injected extension player <=== WebRTC output === encode/composite
                 |
                 +-- positioned over the selected page video
```

Native Messaging is used only for small control messages. Video never travels through its JSON/stdin protocol.

## 4. Cross-browser extension architecture

Maintain one TypeScript codebase and produce two extension packages:

- `reversewarp-chromium`: Chrome and Edge.
- `reversewarp-firefox`: Firefox.

Shared modules cover element discovery, overlay/player behavior, signaling, state management, options, diagnostics, and the native-host protocol. Browser-specific adapters cover capture, background lifecycle, manifest generation, and native-host registration.

### Browser capability matrix

| Capability | Chrome | Edge | Firefox |
|---|---|---|---|
| Extension format | Manifest V3 | Manifest V3 Chromium build | Manifest V3 Firefox build |
| Background runtime | Service worker | Service worker | Background scripts/document |
| Preferred tab capture | `chrome.tabCapture` | `chrome.tabCapture` | `getDisplayMedia()` with an explicit picker |
| Hidden media context | Offscreen document | Offscreen document | Extension/background or dedicated capture page |
| Native messaging allowlist | `allowed_origins` | `allowed_origins` | `allowed_extensions` |
| Windows native-host registry | Chrome key | Edge key | Mozilla key |
| Shared processed-video player | WebRTC extension iframe | WebRTC extension iframe | WebRTC extension iframe |

Firefox must not pretend to have silent active-tab capture. Its adapter opens a small extension capture page and invokes `getDisplayMedia()`, allowing the user to select the desired tab or window. The DOM-video path described below may avoid whole-tab capture when the page exposes a capturable media stream.

### Capture strategies

Implement two ordered strategies behind a common `CaptureAdapter` interface:

1. **DOM media capture:** when permitted, capture the selected `HTMLMediaElement` using `captureStream()`. This avoids browser chrome and unrelated page content and is the preferred cross-browser path.
2. **Tab/display capture fallback:** Chrome and Edge use `tabCapture` after the toolbar click. Firefox uses `getDisplayMedia()` and requires the user to choose the capture surface.

If neither strategy is available, fail clearly and leave the original video unchanged. Protected media is unsupported.

### Chromium Manifest V3 permissions

- `activeTab`
- `tabCapture`
- `offscreen`
- `scripting`
- `nativeMessaging`
- `storage`
- A narrowly scoped localhost host permission for signaling and health checks

Avoid broad site permissions in the MVP. Capture begins only after the user clicks the extension action.

### Firefox Manifest V3 permissions

- `activeTab`
- `scripting`
- `nativeMessaging`
- `storage`
- A narrowly scoped localhost permission
- Explicit Gecko extension ID through `browser_specific_settings`

Firefox does not use the Chromium `offscreen` or `tabCapture` permissions in this design. Capture remains user initiated.

### Components

#### Background controller

- Receives the toolbar action.
- Determines the active tab and verifies that capture is permitted.
- Starts or connects to the native host.
- Requests a short-lived, single-session token and local WebRTC endpoint.
- Starts the browser-specific capture adapter.
- On Chromium, creates the offscreen document and obtains the tab media-stream ID.
- On Firefox, opens the extension capture page and invokes the display-media picker when DOM capture is unavailable.
- Sends session metadata to the capture context and content script.
- Maintains state: `idle`, `starting`, `live`, `bypass`, `failed`, `stopping`.

#### Capture context

- On Chromium, the offscreen document converts the tab-capture ID into a `MediaStream`.
- On Firefox, a dedicated extension page owns the `getDisplayMedia()` stream.
- When DOM capture is available, the page-side capture relay supplies the selected media element's stream.
- Sends the captured video track to the local service over WebRTC.
- Routes source audio locally so tab audio remains audible.
- Does not persist frames.
- Stops all tracks immediately when capture is stopped or the tab closes.

#### Content script

- Enumerates visible `HTMLVideoElement` candidates.
- Chooses the largest actively playing element by default.
- Lets the user select a different element when the choice is ambiguous.
- Records the target element's rectangle, stacking context, fullscreen state, and resize changes.
- Mounts a web-accessible extension player iframe over the selected element.
- Leaves the original element available for immediate fail-open bypass.

#### Player iframe

- Receives the processed WebRTC stream directly from the local service.
- Provides four modes: corrected, original, heatmap, and split comparison.
- Displays latency, detection confidence, dropped-frame count, and GPU state.
- Displays an always-visible `Estimated reconstruction` indicator.
- Mirrors play/pause, fullscreen, resize, scrolling, and picture-in-picture state where feasible.

## 5. Local service

### Rust control and streaming process

Use Rust for the long-running native component:

- `tokio` for asynchronous runtime.
- `axum` for localhost health and WebRTC signaling endpoints.
- GStreamer or FFmpeg bindings/processes for decode, color conversion, and encode.
- WebRTC implementation for browser input and output.
- Windows named pipe or loopback gRPC connection to the Python inference worker.
- Structured JSON logs without image contents.
- Bounded frame queues and explicit backpressure.

Responsibilities:

- Validate the extension origin and per-session token.
- Refuse non-loopback clients in local-only mode.
- Launch and supervise the FAL inference worker.
- Decode incoming frames into GPU-friendly surfaces where supported.
- Track timestamps and preserve audio/video synchronization.
- Drop stale frames instead of accumulating latency.
- Reconnect or fail open when inference stops.

### Python inference worker

Retain FALdetector's existing PyTorch implementation initially.

Responsibilities:

- Load the global classifier and local inverse-warp model once.
- Accept only decoded face crops and associated metadata.
- Return manipulation probability, predicted displacement field, heatmap, and confidence.
- Batch multiple faces only when the latency budget permits.
- Never read arbitrary paths supplied by browser content.

Later optimization may export compatible portions to ONNX or TensorRT, but model equivalence must be tested before replacing the reference implementation.

## 6. Video-processing pipeline

For each frame:

1. Decode and convert to the model's expected color format.
2. Detect faces at a configurable interval.
3. Track faces between detector frames.
4. Estimate landmarks and create a stable aligned crop.
5. Reject unsuitable crops: too small, profile, occluded, blurred, or low confidence.
6. Run the FAL global classifier.
7. If warranted, run the FAL local displacement predictor.
8. Transform the predicted field from crop coordinates into frame coordinates.
9. Propagate the field with optical flow between inference frames.
10. Smooth the field over time with confidence-weighted filtering.
11. Clamp implausible displacement and acceleration.
12. Apply the inverse warp.
13. Composite with a segmentation-aware feathered mask.
14. Generate optional heatmap and split-screen diagnostic surfaces.
15. Encode and publish the processed frame.

### Temporal consistency

Temporal consistency is the highest-risk technical component. The first implementation should combine:

- Persistent face IDs.
- Landmark stabilization.
- Forward/backward optical-flow consistency checks.
- Exponential smoothing of the displacement field.
- Scene-cut resets.
- Confidence decay when inference is skipped.
- Immediate bypass when tracking is lost.

## 7. GPU allocation

### Primary target: RTX 4080

Use the 4080 for:

- Face detection and landmarks.
- FAL inference.
- Optical flow.
- Segmentation.
- Optional restoration.
- NVDEC/NVENC processing.

The A4000 remains a secondary deployment target for one 1080p stream after the pipeline is validated. Output quality at identical model settings should match, but the 4080 provides more headroom for temporal processing and lower latency.

## 8. Privacy and safety requirements

- Local loopback networking by default.
- No cloud API calls, analytics, or telemetry.
- No frame persistence unless the user explicitly enables recording.
- Original files remain immutable in offline mode.
- Every saved output includes a sidecar manifest identifying it as an estimated reconstruction.
- Session tokens are random, short lived, single use, and bound to the extension ID.
- Native messages are schema validated and origin checked.
- The local service never accepts arbitrary command lines or filesystem paths from a web page.
- Browser-page content is treated as untrusted.
- A visible capture indicator and one-click stop control are mandatory.
- On crash, timeout, tab navigation, or GPU failure, reveal the original video and terminate capture tracks.

## 9. Repository layout

```text
reverse-video-warp/
  PROJECT_OUTLINE.md
  extension/
    manifests/
      chromium.json
      firefox.json
    src/
      background/
        chromium-service-worker.ts
        firefox-background.ts
      capture/
        capture-adapter.ts
        chromium-tab-capture.ts
        firefox-display-capture.ts
        dom-media-capture.ts
      offscreen.html
      offscreen.ts
      firefox-capture.html
      firefox-capture.ts
    content-script.ts
    player.html
    player.ts
    options.html
    options.ts
  native-host/
    Cargo.toml
    src/
      main.rs
      native_messaging.rs
      signaling.rs
      session.rs
      pipeline.rs
      metrics.rs
  inference-worker/
    requirements.lock
    worker.py
    fal_adapter.py
    protocol.py
  pipelines/
    ffmpeg/
    gstreamer/
  tests/
    fixtures/
    extension/
    integration/
    quality/
  installer/
    windows/
      native-host-chrome.json
      native-host-edge.json
      native-host-firefox.json
      install.ps1
      uninstall.ps1
```

## 10. Delivery phases

### Phase 0 — reproducible FAL baseline

- Pin Python, PyTorch, CUDA, dlib, and FAL weights.
- Run the released validation examples.
- Record reference hashes and output metrics.
- Confirm the 4080 produces results equivalent to the reference implementation.

Acceptance: identical or tolerance-bounded outputs for the fixed test set.

### Phase 1 — offline video prototype

- Decode a file with FFmpeg.
- Detect and track one face.
- Apply FAL per selected frame.
- Add temporal smoothing and encode a corrected file.
- Produce heatmap and split-screen outputs.

Acceptance: no crashes, timestamps preserved, audio synchronized, and visibly reduced frame-to-frame warp jitter on the test clips.

### Phase 2 — local WebRTC loop

- Implement browser-to-service and service-to-browser WebRTC.
- Use synthetic frames before enabling the model.
- Measure glass-to-glass latency and dropped frames.
- Implement bounded queues and fail-open behavior.

Acceptance: stable 30-minute loopback session without unbounded memory growth or latency accumulation.

### Phase 3 — Chrome and Edge extension MVP

- Add explicit tab capture.
- Select and overlay a target video element.
- Preserve audio.
- Add stop, bypass, comparison, and diagnostic controls.
- Install the Rust native host with a development extension allowlist.

Acceptance: capture and replacement work across a small allowlisted test matrix of ordinary, non-DRM HTML5 video pages.

### Phase 4 — Firefox extension MVP

- Package the shared WebExtension code with the Firefox manifest.
- Implement DOM media capture where permitted.
- Implement the `getDisplayMedia()` fallback and explicit source picker.
- Install the Firefox native-host manifest and registry entry.
- Verify background lifecycle and browser restart recovery independently from Chromium.

Acceptance: the same player, local service, safety behavior, and diagnostic controls work in Firefox, with browser-specific capture differences documented in the UI.

### Phase 5 — integrated live reconstruction

- Connect the offline pipeline to the live frame path.
- Tune detector cadence, flow propagation, and confidence thresholds.
- Add overload policies and resolution fallback.

Acceptance targets for a single frontal face on the 4080:

- 1080p input remains interactive.
- No steadily increasing latency.
- Automatic bypass within one second of tracking or service failure.
- No writes of source frames in default mode.
- Comparison mode clearly exposes artifacts and uncertainty.

### Phase 6 — hardening and packaging

- Threat-model extension, signaling, and native-host boundaries.
- Fuzz native-message and signaling parsers.
- Add signed installer and deterministic uninstall.
- Add model/license notices and checksum verification.
- Add crash recovery, log rotation, and GPU health checks.

Acceptance: fresh-machine installation, browser restart recovery, update rollback, and complete removal are tested.

## 11. Test strategy

### Functional tests

- Start/stop and repeated session creation.
- Navigation, reload, fullscreen, resize, and tab close.
- Chrome, Edge, and Firefox behavior for every lifecycle test.
- Firefox picker cancellation and Chromium capture-permission denial.
- Paused, seeking, muted, and variable-frame-rate video.
- No face, one face, multiple faces, profile, occlusion, and scene cuts.
- GPU unavailable, worker crash, encoder failure, and WebRTC disconnect.

### Quality tests

- Landmark jitter and displacement-field acceleration.
- Temporal warping consistency.
- FAL classification precision on held-out samples.
- Identity similarity before and after correction.
- Boundary/compositing artifacts.
- Side-by-side human review with the manipulation heatmap visible.

### Performance tests

- End-to-end latency distribution, not just average latency.
- Decode, detection, FAL, flow, composite, encode, and network stage timing.
- GPU utilization and VRAM high-water mark.
- Dropped frames and queue depth.
- 30-minute and 4-hour soak tests.

## 12. Major risks

| Risk | Mitigation |
|---|---|
| Frame-by-frame shimmer | Tracking, optical-flow propagation, field smoothing and scene resets |
| FAL dataset bias | Narrow claims, confidence gates and validation on representative clips |
| Reconstruction mistaken for truth | Permanent labeling, original comparison and sidecar provenance |
| Browser extension compromise | Minimal permissions, origin validation and capability tokens |
| Native messaging bottleneck | Control only; WebRTC carries video |
| Latency accumulation | Bounded single/latest-frame queues and stale-frame dropping |
| Page layout changes | ResizeObserver, fullscreen listeners and fail-open original element |
| Browser capture API differences | Shared adapter contract plus browser-specific implementations and test suites |
| Firefox requires a capture picker | Make the extra user gesture explicit and remember no source beyond the active session |
| Protected media | Declare unsupported; do not attempt circumvention |

## 13. First engineering milestone

Before writing the extension, build an offline command-line demonstrator:

```text
reversewarp process input.mp4 \
  --output corrected.mp4 \
  --diagnostic heatmap.mp4 \
  --comparison split.mp4 \
  --device cuda:0
```

This isolates the hardest problem—stable inverse warping across time—from browser capture, WebRTC, and overlay behavior. The browser extension should be added only after the corrected offline video is demonstrably stable.

## 14. Reference platform constraints

- Chrome and Edge `tabCapture` require a user invocation such as clicking the extension action.
- Chromium Manifest V3 service workers do not provide DOM/media processing; an offscreen document is needed for media-stream handling.
- A Chromium stream ID created by the service worker can be consumed by an offscreen document on current browser versions.
- Firefox's Manifest V3 background model differs from Chromium and does not use the same service-worker/offscreen combination.
- Firefox fallback capture uses `getDisplayMedia()`, which prompts the user to select and grant a display surface.
- Firefox native-host manifests use `allowed_extensions`; Chrome and Edge use `allowed_origins`.
- Native Messaging must validate the calling extension identity and content-script-derived input on every browser.

Official references:

- https://developer.chrome.com/docs/extensions/reference/api/tabCapture
- https://developer.chrome.com/docs/extensions/reference/api/offscreen
- https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture
- https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia
- https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Chrome_incompatibilities
- https://github.com/PeterWang512/FALdetector
