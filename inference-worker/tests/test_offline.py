from __future__ import annotations

import unittest

import numpy as np
import torch

from reversewarp_worker.offline import (
    _clip_box,
    _feather_composite,
    _flow_heatmap,
    _padded_box,
    _resize_field,
)


class OfflineUtilityTests(unittest.TestCase):
    def test_box_padding_stays_inside_frame(self) -> None:
        box = _padded_box((0, 0, 20, 20), (40, 50))
        x, y, width, height = box
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + width, 50)
        self.assertLessEqual(y + height, 40)

    def test_clip_box_keeps_minimum_size(self) -> None:
        self.assertEqual(_clip_box((99, 99, 1, 1), (100, 100)), (98, 98, 2, 2))

    def test_resize_field_scales_pixel_units(self) -> None:
        field = torch.ones((2, 4, 2), dtype=torch.float32)
        result = _resize_field(field, 8, 6)
        self.assertEqual(tuple(result.shape), (6, 8, 2))
        torch.testing.assert_close(result[..., 0], torch.full((6, 8), 2.0))
        torch.testing.assert_close(result[..., 1], torch.full((6, 8), 3.0))

    def test_feather_composite_preserves_shape(self) -> None:
        original = np.zeros((40, 30, 3), dtype=np.uint8)
        warped = np.full_like(original, 255)
        result = _feather_composite(original, warped)
        self.assertEqual(result.shape, original.shape)
        self.assertGreater(int(result[20, 15, 0]), int(result[0, 0, 0]))

    def test_zero_flow_heatmap_is_black(self) -> None:
        result = _flow_heatmap(torch.zeros((4, 5, 2), dtype=torch.float32))
        self.assertTrue(np.all(result == 0))


if __name__ == "__main__":
    unittest.main()
