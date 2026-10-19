from __future__ import annotations

import unittest

import torch

from reversewarp_worker.temporal import TemporalFieldSmoother


class TemporalFieldSmootherTests(unittest.TestCase):
    def test_limits_motion_and_weights_confidence(self) -> None:
        smoother = TemporalFieldSmoother(base_alpha=0.5, max_delta_pixels=4.0)
        first = torch.zeros((2, 2, 2), dtype=torch.float32)
        second = torch.full((2, 2, 2), 20.0, dtype=torch.float32)
        smoother.update(first, confidence=1.0)
        result = smoother.update(second, confidence=0.5)
        self.assertIsNotNone(result)
        torch.testing.assert_close(result, torch.ones_like(second))

    def test_low_confidence_resets_tracking(self) -> None:
        smoother = TemporalFieldSmoother(confidence_floor=0.25)
        field = torch.zeros((2, 2, 2), dtype=torch.float32)
        self.assertIsNotNone(smoother.update(field, confidence=1.0))
        self.assertIsNone(smoother.update(field, confidence=0.1))
        replacement = torch.full_like(field, 3.0)
        torch.testing.assert_close(
            smoother.update(replacement, confidence=1.0), replacement
        )

