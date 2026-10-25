"""Train the SpaceNet U-Net and select a checkpoint from image-held-out IoU."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from lagos_buildings.model import UNet, dice_focal_loss


class TileDataset(Dataset):
    def __init__(self, root: Path, split: str) -> None:
        self.images = sorted((root / "images" / split).glob("*.npy"))
        self.masks = root / "masks" / split
        missing = [path.name for path in self.images if not (self.masks / path.name).exists()]
        if not self.images or missing:
            raise FileNotFoundError(f"No complete {split} tile pairs under {root}; missing masks: {missing[:3]}")

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image = np.load(self.images[index]).astype(np.float32)
        mask = np.load(self.masks / self.images[index].name).astype(np.float32)
        image = image / 255.0
        return torch.from_numpy(image), torch.from_numpy(mask[None, ...])


def _epoch(model, loader, optimizer, device, training: bool, threshold: float) -> tuple[float, dict[str, float]]:
    model.train(training)
    loss_sum = 0.0
    count = 0
    tp = fp = fn = 0
    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            logits = model(images)
            loss = dice_focal_loss(logits, masks)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            loss_sum += loss.item() * len(images)
            count += len(images)
            predicted = torch.sigmoid(logits.detach()) >= threshold
            truth = masks >= 0.5
            tp += (predicted & truth).sum().item()
            fp += (predicted & ~truth).sum().item()
            fn += (~predicted & truth).sum().item()
    iou = tp / max(tp + fp + fn, 1)
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    metrics = {"iou": float(iou), "f1": float(f1), "threshold": threshold}
    return loss_sum / max(count, 1), metrics


def train(
    tiles: Path,
    output: Path,
    *,
    epochs: int = 30,
    batch_size: int = 8,
    learning_rate: float = 1e-4,
    base_channels: int = 32,
    seed: int = 42,
    threshold: float = 0.5,
) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    manifest = json.loads((tiles / "manifest.json").read_text(encoding="utf-8"))
    normalization = manifest["rgb_normalization"]
    train_data = TileDataset(tiles, "train")
    validation_data = TileDataset(tiles, "validation")
    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=device.type == "cuda")
    validation_loader = DataLoader(validation_data, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=device.type == "cuda")

    model = UNet(in_channels=3, base_channels=base_channels).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    output.parent.mkdir(parents=True, exist_ok=True)
    history = []
    best_iou = -1.0
    best_f1 = 0.0
    for epoch in range(1, epochs + 1):
        train_loss, train_metrics = _epoch(model, train_loader, optimizer, device, True, threshold)
        val_loss, val_metrics = _epoch(model, validation_loader, optimizer, device, False, threshold)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_iou": train_metrics["iou"],
            "train_f1": train_metrics["f1"],
            "validation_loss": val_loss,
            "validation_iou": val_metrics["iou"],
            "validation_f1": val_metrics["f1"],
            "threshold": threshold,
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if val_metrics["iou"] > best_iou:
            best_iou = val_metrics["iou"]
            best_f1 = val_metrics["f1"]
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "architecture": "U-Net",
                "in_channels": 3,
                "base_channels": base_channels,
                "tile_size": int(np.load(train_data.images[0], mmap_mode="r").shape[-1]),
                "image_scale": 255.0,
                "image_lower": normalization["lower"],
                "image_upper": normalization["upper"],
                "threshold": threshold,
                "best_validation_iou": best_iou,
                "best_validation_f1": val_metrics["f1"],
                "training_source": "SpaceNet 2 AOI 2 Vegas RGB-PanSharpen",
                "seed": seed,
            }
            torch.save(checkpoint, output)

    metrics = {
        "architecture": "U-Net",
        "training_source": "SpaceNet 2 AOI 2 Vegas RGB-PanSharpen with rasterized building GeoJSON masks",
        "split": "source-image-level train/validation split",
        "seed": seed,
        "base_channels": base_channels,
        "train_source_images": len(manifest["train_source_image_ids"]),
        "validation_source_images": len(manifest["validation_source_image_ids"]),
        "train_source_image_ids": manifest["train_source_image_ids"],
        "validation_source_image_ids": manifest["validation_source_image_ids"],
        "loss": "soft Dice + binary focal loss",
        "optimizer": "Adam",
        "device": str(device),
        "train_tiles": len(train_data),
        "validation_tiles": len(validation_data),
        "best_validation_iou": best_iou,
        "best_validation_f1": best_f1,
        "threshold": threshold,
        "epochs": epochs,
        "history": history,
        "checkpoint": str(output),
    }
    metrics_path = output.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles", type=Path, default=Path("data/spacenet_tiles"))
    parser.add_argument("--output", type=Path, default=Path("outputs/unet_spacenet2_vegas.pt"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--base-channels", type=int, default=32)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = train(
        args.tiles, args.output, epochs=args.epochs, batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        base_channels=args.base_channels, seed=args.seed, threshold=args.threshold,
    )
    print(json.dumps({key: result[key] for key in ("best_validation_iou", "best_validation_f1", "checkpoint")}, indent=2))


if __name__ == "__main__":
    main()
