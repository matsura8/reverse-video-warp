# Security policy

ReverseWarp Local is a research MVP and does not yet have a signed production release.

Please report suspected security issues privately through GitHub's private vulnerability reporting feature once it is enabled for the repository. Do not attach captured video, face crops, model outputs, credentials, tokens, or other personal data to a public issue.

## Security invariants

- Browser and media-derived input is untrusted.
- The native service binds to loopback only.
- Session tokens contain 256 bits of randomness, expire after 30 minutes, are bound to one normalized extension origin, and are revoked on Stop.
- Native messaging carries control data only, never video frames.
- Live frames use an authenticated, bounded binary endpoint on `127.0.0.1`; the browser cannot supply paths or commands to the worker.
- The CUDA worker accepts only bounded base64 image messages from its supervising Rust process.
- Source files are immutable and outputs never overwrite existing files.
- No cloud APIs, analytics, or telemetry are used.
- Failures reveal the original video and stop capture tracks.

Changes that weaken an invariant require an explicit threat-model update and focused tests.

