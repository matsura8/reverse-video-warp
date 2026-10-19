# ReverseWarp inference worker

The inference worker owns GPU model execution. It communicates through newline-delimited JSON on standard input/output; diagnostics go to standard error so protocol responses stay machine-readable.

Production startup is CUDA-first and fail-closed. A `cuda:N` device must resolve to an available NVIDIA device. CPU execution is disabled unless `--allow-cpu` is supplied explicitly for tests or debugging.

## Local CUDA environment

Run `installer/windows/setup-cuda-worker.ps1`. The script creates an isolated Python 3.12 environment under `%LOCALAPPDATA%\ReverseWarp\venv` and installs the pinned CUDA wheels. The environment is outside this network-share checkout because Windows may block execution of generated binaries from SMB paths.

## Protocol

Requests and responses contain a protocol version and request ID. The initial supported operation is `health`:

```json
{"version":1,"requestId":"probe-1","operation":"health"}
```

The worker never accepts command lines or arbitrary filesystem paths through this protocol.

