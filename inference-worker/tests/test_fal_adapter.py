from __future__ import annotations

import unittest

import torch

from reversewarp_worker.fal_adapter import FalAdapterError, preprocess_face


class FalAdapterTests(unittest.TestCase):
    def test_preprocess_matches_short_side_contract(self) -> None:
        face = torch.zeros((200, 100, 3), dtype=torch.uint8)
        result = preprocess_face(face, device="cpu")
        self.assertEqual(tuple(result.shape), (3, 800, 400))
        self.assertEqual(result.dtype, torch.float32)

    def test_preprocess_rejects_wrong_layout(self) -> None:
        face = torch.zeros((3, 100, 100), dtype=torch.uint8)
        with self.assertRaisesRegex(FalAdapterError, "HxWx3"):
            preprocess_face(face, device="cpu")

