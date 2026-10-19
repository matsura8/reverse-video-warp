from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


CUDA_DEVICE = re.compile(r"^cuda:(0|[1-9][0-9]*)$")


class DeviceError(RuntimeError):
    """Raised when the requested inference device is unsafe or unavailable."""


@dataclass(frozen=True)
class DeviceInfo:
    requested: str
    resolved: str
    kind: str
    name: str
    cuda_available: bool
    cuda_version: str | None
    torch_version: str
    device_count: int
    total_memory_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_device(device: str, *, allow_cpu: bool = False) -> DeviceInfo:
    try:
        import torch
    except ImportError as error:
        raise DeviceError(
            "PyTorch is not installed; run installer/windows/setup-cuda-worker.ps1"
        ) from error

    if device == "cpu":
        if not allow_cpu:
            raise DeviceError("CPU inference is disabled; request a cuda:N device")
        return DeviceInfo(
            requested=device,
            resolved="cpu",
            kind="cpu",
            name="CPU debug fallback",
            cuda_available=bool(torch.cuda.is_available()),
            cuda_version=torch.version.cuda,
            torch_version=torch.__version__,
            device_count=int(torch.cuda.device_count()),
            total_memory_bytes=None,
        )

    match = CUDA_DEVICE.fullmatch(device)
    if match is None:
        raise DeviceError("device must be cuda:N (production) or cpu (explicit debug only)")
    if not torch.cuda.is_available():
        raise DeviceError(
            "CUDA is unavailable in PyTorch; a CPU-only wheel or inaccessible NVIDIA driver was detected"
        )

    index = int(match.group(1))
    count = int(torch.cuda.device_count())
    if index >= count:
        raise DeviceError(f"requested {device}, but only {count} CUDA device(s) are visible")

    properties = torch.cuda.get_device_properties(index)
    # Force CUDA context creation now so startup fails before accepting frames.
    torch.empty(1, device=device)
    return DeviceInfo(
        requested=device,
        resolved=f"cuda:{index}",
        kind="cuda",
        name=properties.name,
        cuda_available=True,
        cuda_version=torch.version.cuda,
        torch_version=torch.__version__,
        device_count=count,
        total_memory_bytes=int(properties.total_memory),
    )

