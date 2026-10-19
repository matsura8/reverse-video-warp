from __future__ import annotations

from dataclasses import dataclass


class TemporalError(ValueError):
    """Raised when temporal smoothing input is invalid."""


@dataclass
class TemporalFieldSmoother:
    """Confidence-weighted EMA with per-frame acceleration limiting."""

    base_alpha: float = 0.35
    max_delta_pixels: float = 6.0
    confidence_floor: float = 0.15
    _previous: "torch.Tensor | None" = None

    def __post_init__(self) -> None:
        if not 0.0 < self.base_alpha <= 1.0:
            raise TemporalError("base_alpha must be in (0, 1]")
        if self.max_delta_pixels <= 0.0:
            raise TemporalError("max_delta_pixels must be positive")
        if not 0.0 <= self.confidence_floor <= 1.0:
            raise TemporalError("confidence_floor must be in [0, 1]")

    def reset(self) -> None:
        self._previous = None

    def update(self, field: "torch.Tensor", *, confidence: float) -> "torch.Tensor | None":
        import torch

        if field.dtype != torch.float32 or field.ndim != 3 or field.shape[-1] != 2:
            raise TemporalError("field must be an HxWx2 float32 tensor")
        if not torch.isfinite(field).all():
            raise TemporalError("field contains NaN or infinity")
        if not 0.0 <= confidence <= 1.0:
            raise TemporalError("confidence must be in [0, 1]")
        if confidence < self.confidence_floor:
            self.reset()
            return None

        if self._previous is None or self._previous.shape != field.shape:
            self._previous = field.detach().clone()
            return self._previous

        delta = (field - self._previous).clamp(
            -self.max_delta_pixels, self.max_delta_pixels
        )
        alpha = self.base_alpha * confidence
        self._previous = (self._previous + (delta * alpha)).detach()
        return self._previous

