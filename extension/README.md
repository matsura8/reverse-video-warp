# Browser extensions

One TypeScript source tree builds the Chromium MV3 package for Edge/Chrome and the Firefox MV3 package.

```powershell
npm ci --ignore-scripts
npm test
```

The build output is intentionally ignored because `installer/windows/install.ps1` rebuilds it deterministically. Chromium uses stable extension ID `ghpmamlndagjlmhhimhlilhngpenmbol`; Firefox uses `reversewarp@maxpowerit.local`.

Capture starts only from the toolbar action. Direct DOM-video capture is preferred. Cross-origin video falls back to an offscreen `tabCapture` context on Chromium or an explicit `getDisplayMedia()` picker on Firefox. The source element is never removed. The generated canvas is exposed as a `MediaStream` to an overlay `<video>`, while original audio remains local. Three consecutive frame failures trigger fail-open teardown.
