# Integration acceptance

`edge_acceptance.py` tests the installed Chromium package against a same-origin, non-protected HTML5 fixture and the real installed Rust/CUDA runtime. It makes a temporary extension copy that auto-starts only on the localhost fixture because WebDriver cannot invoke browser-toolbar actions. The installed production package remains user-initiated and unmodified.

```powershell
python -m http.server 18765 --bind 127.0.0.1 --directory tests/fixtures
$env:REVERSEWARP_THRESHOLD = '0'
& "$env:LOCALAPPDATA\ReverseWarp\test-venv\Scripts\python.exe" tests/integration/edge_acceptance.py
```

Acceptance requires:

- Microsoft Edge loads the packaged extension and installed native host.
- A frame reaches the persistent CUDA worker and returns corrected.
- The source `<video>` remains in the page.
- A processed `<video>` is embedded over it with the `Estimated reconstruction` label.
- Stop removes the overlay and reveals the original.

The forced zero threshold is limited to the acceptance process environment. Normal installed behavior defaults to a 0.5 manipulation-probability gate.

## One-site streaming checks

`edge_single_site.py` exercises the installed production extension through its
real `Ctrl+Shift+Y` action. Run one provider at a time so failures and site
behavior remain attributable to a single player:

```powershell
$env:REVERSEWARP_THRESHOLD = '0'
& "$env:LOCALAPPDATA\ReverseWarp\test-venv\Scripts\python.exe" `
  tests/integration/edge_single_site.py `
  --name Dailymotion `
  --url 'https://www.dailymotion.com/video/xbkov2a'
```

The check waits for either a top-level HTML5 video or a visible embedded player,
verifies that a processed overlay is embedded, activates Stop, and confirms the
original player is revealed. Streaming frames are processed transiently and are
not recorded or saved.
