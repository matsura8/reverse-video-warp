# Security policy

ReverseWarp Local is an early research project and does not yet have a supported production release.

Please report suspected security issues privately through GitHub's private vulnerability reporting feature once it is enabled for the repository. Do not attach captured video, face crops, model outputs, credentials, tokens, or other personal data to a public issue.

## Security invariants

- Browser and media-derived input is untrusted.
- The native service binds to loopback only.
- Session tokens are short lived, single use, and extension-bound.
- Native messaging carries control data only, never video frames.
- Source files are immutable and outputs never overwrite existing files.
- No cloud APIs, analytics, or telemetry are used.
- Failures reveal the original video and stop capture tracks.

Changes that weaken an invariant require an explicit threat-model update and focused tests.

