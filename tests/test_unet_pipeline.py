import unittest

import numpy as np
import torch

from lagos_buildings.model import UNet, dice_focal_loss
from lagos_buildings.prepare import _windows


class UNetModelTests(unittest.TestCase):
    def test_forward_preserves_tile_shape_and_returns_one_logit_band(self):
        torch.set_num_threads(1)
        model = UNet(in_channels=3, base_channels=4).eval()
        with torch.no_grad():
            logits = model(torch.rand(2, 3, 32, 32))
        self.assertEqual(tuple(logits.shape), (2, 1, 32, 32))

    def test_dice_focal_loss_is_finite_and_differentiable(self):
        logits = torch.randn(2, 1, 32, 32, requires_grad=True)
        target = torch.zeros(2, 1, 32, 32)
        target[:, :, 8:20, 10:23] = 1
        loss = dice_focal_loss(logits, target)
        self.assertTrue(torch.isfinite(loss).item())
        loss.backward()
        self.assertIsNotNone(logits.grad)
        self.assertTrue(torch.isfinite(logits.grad).all().item())

    def test_windows_cover_edges_without_exceeding_tile_size(self):
        positions = _windows(length=650, tile_size=256, stride=256)
        self.assertEqual(positions, [0, 256, 394])
        covered = np.zeros(650, dtype=bool)
        for start in positions:
            covered[start : start + 256] = True
        self.assertTrue(covered.all())


if __name__ == "__main__":
    unittest.main()
