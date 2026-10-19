from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class WarpError(ValueError):
    """Raised when a frame or displacement field violates the CUDA contract."""


@dataclass(frozen=True)
class SelfTestResult:
    device: str
    dtype: str
    shape: list[int]
    identity_max_error: int
    deterministic: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inverse_warp_rgb(
    image: "torch.Tensor",
    displacement_pixels: "torch.Tensor",
    *,
    device: str,
    max_displacement_pixels: float = 96.0,
) -> "torch.Tensor":
    """Apply an inverse sampling warp to one uint8 RGB frame.

    `displacement_pixels[y, x]` stores `(dx, dy)` in source-pixel units.
    Positive `dx` samples to the right and positive `dy` samples downward.
    Float32 math is retained for reconstruction quality and repeatability.
    """
    import torch
    import torch.nn.functional as functional

    if image.dtype != torch.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise WarpError("image must be an HxWx3 uint8 tensor")
    height, width, _ = image.shape
    if height < 2 or width < 2:
        raise WarpError("image dimensions must both be at least 2 pixels")
    if displacement_pixels.dtype != torch.float32:
        raise WarpError("displacement field must use float32")
    if tuple(displacement_pixels.shape) != (height, width, 2):
        raise WarpError("displacement field must have shape HxWx2")
    if max_displacement_pixels <= 0:
        raise WarpError("max displacement must be positive")

    image_gpu = image.to(device=device, dtype=torch.float32, non_blocking=True)
    field_gpu = displacement_pixels.to(device=device, dtype=torch.float32, non_blocking=True)
    if not torch.isfinite(field_gpu).all():
        raise WarpError("displacement field contains NaN or infinity")
    field_gpu = field_gpu.clamp(-max_displacement_pixels, max_displacement_pixels)

    y_coordinates, x_coordinates = torch.meshgrid(
        torch.arange(height, device=device, dtype=torch.float32),
        torch.arange(width, device=device, dtype=torch.float32),
        indexing="ij",
    )
    sample_x = x_coordinates + field_gpu[..., 0]
    sample_y = y_coordinates + field_gpu[..., 1]
    grid = torch.stack(
        (
            (sample_x * (2.0 / (width - 1))) - 1.0,
            (sample_y * (2.0 / (height - 1))) - 1.0,
        ),
        dim=-1,
    ).unsqueeze(0)
    channels_first = image_gpu.permute(2, 0, 1).unsqueeze(0)
    warped = functional.grid_sample(
        channels_first,
        grid,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )
    return warped.squeeze(0).permute(1, 2, 0).round().clamp(0, 255).to(torch.uint8)


def run_cuda_self_test(device: str) -> SelfTestResult:
    import torch

    height = 64
    width = 96
    y, x = torch.meshgrid(torch.arange(height), torch.arange(width), indexing="ij")
    image = torch.stack(((x * 3) % 256, (y * 5) % 256, (x + y) % 256), dim=-1).to(
        torch.uint8
    )
    field = torch.zeros((height, width, 2), dtype=torch.float32)
    first = inverse_warp_rgb(image, field, device=device)
    second = inverse_warp_rgb(image, field, device=device)
    torch.cuda.synchronize(device)
    maximum_error = int((first.cpu().to(torch.int16) - image.to(torch.int16)).abs().max())
    return SelfTestResult(
        device=device,
        dtype="float32",
        shape=[height, width, 3],
        identity_max_error=maximum_error,
        deterministic=bool(torch.equal(first, second)),
    )

