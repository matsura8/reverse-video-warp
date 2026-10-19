from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
from pathlib import Path
import sys
from typing import Any


class FalAdapterError(RuntimeError):
    """Raised when the pinned FAL baseline cannot be loaded safely."""


@dataclass(frozen=True)
class FalResult:
    manipulation_probability: float
    displacement: "torch.Tensor"


@dataclass(frozen=True)
class FalSelfTestResult:
    device: str
    manipulation_probability: float
    displacement_shape: list[int]
    displacement_finite: bool
    global_parameters: int
    local_parameters: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FalModels:
    def __init__(self, root: Path, *, device: str) -> None:
        import torch

        if not device.startswith("cuda:"):
            raise FalAdapterError("FAL production inference requires a CUDA device")
        global_weights = root / "weights" / "global.pth"
        local_weights = root / "weights" / "local.pth"
        for path in (global_weights, local_weights):
            if not path.is_file():
                raise FalAdapterError(f"required FAL weight is missing: {path}")

        root_text = str(root.resolve())
        sys.path.insert(0, root_text)
        try:
            module = importlib.import_module("networks.drn_seg")
        except (ImportError, OSError) as error:
            raise FalAdapterError(f"failed to import pinned FAL model code: {error}") from error
        finally:
            if sys.path[0] == root_text:
                sys.path.pop(0)

        self.device = device
        self.global_model = module.DRNSub(1)
        self.local_model = module.DRNSeg(2)
        self.global_model.load_state_dict(
            _model_state(torch.load(global_weights, map_location="cpu", weights_only=True))
        )
        self.local_model.load_state_dict(
            _model_state(torch.load(local_weights, map_location="cpu", weights_only=True))
        )
        self.global_model.to(device).eval()
        self.local_model.to(device).eval()

    def infer(self, face_rgb: "torch.Tensor") -> FalResult:
        import torch

        batch = preprocess_face(face_rgb, device=self.device).unsqueeze(0)
        with torch.inference_mode():
            probability = float(self.global_model(batch)[0].sigmoid().item())
            displacement = self.local_model(batch)[0].permute(1, 2, 0).contiguous()
        if not torch.isfinite(displacement).all():
            raise FalAdapterError("FAL local model produced a non-finite displacement field")
        return FalResult(
            manipulation_probability=probability,
            displacement=displacement,
        )

    def self_test(self) -> FalSelfTestResult:
        import torch

        y, x = torch.meshgrid(torch.arange(400), torch.arange(400), indexing="ij")
        face = torch.stack(
            ((x * 3) % 256, (y * 5) % 256, (x + y) % 256), dim=-1
        ).to(torch.uint8)
        result = self.infer(face)
        torch.cuda.synchronize(self.device)
        return FalSelfTestResult(
            device=self.device,
            manipulation_probability=result.manipulation_probability,
            displacement_shape=list(result.displacement.shape),
            displacement_finite=bool(torch.isfinite(result.displacement).all()),
            global_parameters=sum(parameter.numel() for parameter in self.global_model.parameters()),
            local_parameters=sum(parameter.numel() for parameter in self.local_model.parameters()),
        )


def preprocess_face(face_rgb: "torch.Tensor", *, device: str) -> "torch.Tensor":
    import torch
    import torchvision.transforms.functional as vision

    if face_rgb.dtype != torch.uint8 or face_rgb.ndim != 3 or face_rgb.shape[-1] != 3:
        raise FalAdapterError("face crop must be an HxWx3 uint8 tensor")
    height, width, _ = face_rgb.shape
    if height < 2 or width < 2:
        raise FalAdapterError("face crop dimensions must both be at least 2 pixels")
    if width < height:
        resized_width = 400
        resized_height = int(400 * height / width)
    else:
        resized_height = 400
        resized_width = int(400 * width / height)

    tensor = face_rgb.permute(2, 0, 1).to(dtype=torch.float32).div_(255.0)
    tensor = vision.resize(
        tensor,
        [resized_height, resized_width],
        interpolation=vision.InterpolationMode.BICUBIC,
        antialias=True,
    )
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)[:, None, None]
    standard_deviation = torch.tensor(
        [0.229, 0.224, 0.225], dtype=torch.float32
    )[:, None, None]
    return ((tensor - mean) / standard_deviation).to(device=device, non_blocking=True)


def _model_state(checkpoint: object) -> dict[str, Any]:
    if not isinstance(checkpoint, dict) or "model" not in checkpoint:
        raise FalAdapterError("FAL checkpoint does not contain a model state")
    state = checkpoint["model"]
    if not isinstance(state, dict):
        raise FalAdapterError("FAL model state is not a mapping")
    return state

