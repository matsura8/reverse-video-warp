from __future__ import annotations

import unittest

import torch

from reversewarp_worker.warp import WarpError, inverse_warp_rgb


class InverseWarpTests(unittest.TestCase):
    def test_identity_warp_is_exact_on_cpu_debug_path(self) -> None:
        image = torch.arange(4 * 5 * 3, dtype=torch.uint8).reshape(4, 5, 3)
        field = torch.zeros((4, 5, 2), dtype=torch.float32)
        result = inverse_warp_rgb(image, field, device="cpu")
        torch.testing.assert_close(result, image)

    def test_positive_horizontal_displacement_samples_right(self) -> None:
        image = torch.zeros((3, 4, 3), dtype=torch.uint8)
        image[:, :, 0] = torch.tensor([0, 10, 20, 30], dtype=torch.uint8)
        field = torch.zeros((3, 4, 2), dtype=torch.float32)
        field[..., 0] = 1.0
        result = inverse_warp_rgb(image, field, device="cpu")
        self.assertEqual(result[1, :, 0].tolist(), [10, 20, 30, 30])

    def test_rejects_nonfinite_field(self) -> None:
        image = torch.zeros((3, 4, 3), dtype=torch.uint8)
        field = torch.zeros((3, 4, 2), dtype=torch.float32)
        field[0, 0, 0] = float("nan")
        with self.assertRaisesRegex(WarpError, "NaN"):
            inverse_warp_rgb(image, field, device="cpu")


if __name__ == "__main__":
    unittest.main()
