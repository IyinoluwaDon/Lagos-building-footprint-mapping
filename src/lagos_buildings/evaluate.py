"""Evaluate a saved SpaceNet U-Net on a separate, source-image test split."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lagos_buildings.model import UNet
from lagos_buildings.train import TileDataset, _epoch


def evaluate(tiles: Path, checkpoint_path: Path, output: Path) -> dict:
    manifest = json.loads((tiles / "manifest.json").read_text(encoding="utf-8"))
    checkpoint_metrics_path = checkpoint_path.with_suffix(".metrics.json")
    training = json.loads(checkpoint_metrics_path.read_text(encoding="utf-8"))
    test_ids = set(manifest["validation_source_image_ids"])
    seen_ids = set(training["train_source_image_ids"]) | set(training["validation_source_image_ids"])
    overlap = sorted(test_ids & seen_ids, key=int)
    if overlap:
        raise ValueError(f"Test scenes overlap with training/model-selection scenes: {overlap}")
    if not test_ids:
        raise ValueError("The prepared test split contains no held-out source scenes.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model = UNet(
        in_channels=int(checkpoint["in_channels"]),
        base_channels=int(checkpoint["base_channels"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    dataset = TileDataset(tiles, "validation")
    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
    threshold = float(checkpoint["threshold"])
    loss, scores = _epoch(model, loader, optimizer=None, device=device, training=False, threshold=threshold)
    checkpoint_sha256 = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    result = {
        "test_source": manifest["source"],
        "evaluation_split": "unseen SpaceNet source images, excluded from training and checkpoint selection",
        "test_scene_ids": sorted(test_ids, key=int),
        "test_source_images": len(test_ids),
        "test_tiles": len(dataset),
        "architecture": checkpoint["architecture"],
        "base_channels": checkpoint["base_channels"],
        "threshold": threshold,
        "test_loss": loss,
        "test_pixel_iou": scores["iou"],
        "test_pixel_f1": scores["f1"],
        "device": str(device),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha256,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles", type=Path, default=Path("data/spacenet_test_tiles"))
    parser.add_argument("--checkpoint", type=Path, default=Path("outputs/unet_spacenet2_vegas.pt"))
    parser.add_argument("--output", type=Path, default=Path("outputs/unet_spacenet2_vegas.test_metrics.json"))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.tiles, args.checkpoint, args.output), indent=2))


if __name__ == "__main__":
    main()
