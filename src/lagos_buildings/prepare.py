"""Rasterize SpaceNet building polygons and create leakage-safe image/mask tiles."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize


_IMAGE_ID = re.compile(r"img[_-]?(\d+)", re.IGNORECASE)


def _id(path: Path) -> str | None:
    match = _IMAGE_ID.search(path.stem)
    return match.group(1) if match else None


def _pairs(images_dir: Path, labels_dir: Path) -> list[tuple[Path, Path]]:
    image_paths = [path for path in images_dir.rglob("*.tif") if _id(path)]
    label_paths = [path for path in labels_dir.rglob("*.geojson") if _id(path)]
    images = {_id(path): path for path in image_paths}
    labels = {_id(path): path for path in label_paths}
    ids = sorted(images.keys() & labels.keys())
    if not ids:
        raise FileNotFoundError(
            f"No paired SpaceNet image/label IDs found under {images_dir} and {labels_dir}."
        )
    duplicate_images = sorted({key for key in images if sum(_id(path) == key for path in image_paths) > 1})
    duplicate_labels = sorted({key for key in labels if sum(_id(path) == key for path in label_paths) > 1})
    if duplicate_images or duplicate_labels:
        raise ValueError(f"Duplicate image IDs: {duplicate_images[:5]}; label IDs: {duplicate_labels[:5]}")
    return [(images[key], labels[key]) for key in ids]


def _windows(length: int, tile_size: int, stride: int) -> list[int]:
    if length <= tile_size:
        return [0]
    positions = list(range(0, length - tile_size + 1, stride))
    final = length - tile_size
    if positions[-1] != final:
        positions.append(final)
    return positions


def prepare(
    images_dir: Path,
    labels_dir: Path,
    output_dir: Path,
    *,
    tile_size: int = 256,
    stride: int = 256,
    validation_fraction: float = 0.2,
    negative_keep_fraction: float = 0.25,
    seed: int = 42,
) -> dict:
    if tile_size % 16:
        raise ValueError("tile_size must be divisible by 16 for the four-level U-Net.")
    if stride <= 0:
        raise ValueError("stride must be a positive integer.")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1.")
    if not 0 <= negative_keep_fraction <= 1:
        raise ValueError("negative_keep_fraction must be between 0 and 1.")

    pairs = _pairs(images_dir, labels_dir)
    if len(pairs) < 2:
        raise ValueError("At least two paired source images are needed for image-level train/validation split.")
    rng = random.Random(seed)
    image_ids = [(_id(image), image, label) for image, label in pairs]
    shuffled = image_ids.copy()
    rng.shuffle(shuffled)
    n_validation = min(len(shuffled) - 1, max(1, round(len(shuffled) * validation_fraction)))
    validation_ids = {item[0] for item in shuffled[:n_validation]}

    per_image_ranges = []
    for image_id, image_path, _ in image_ids:
        if image_id in validation_ids:
            continue
        with rasterio.open(image_path) as src:
            rgb = src.read((1, 2, 3)).astype(np.float32)
        per_image_ranges.append((
            np.percentile(rgb, 2, axis=(1, 2)),
            np.percentile(rgb, 98, axis=(1, 2)),
        ))
    lower = np.median(np.stack([values[0] for values in per_image_ranges]), axis=0)
    upper = np.median(np.stack([values[1] for values in per_image_ranges]), axis=0)
    if np.any(upper <= lower):
        raise ValueError("Could not derive nonzero RGB normalization ranges from the training images.")

    counts = {"source_images": len(pairs), "tiles": 0, "positive_tiles": 0, "negative_tiles": 0}
    output_dir.mkdir(parents=True, exist_ok=True)
    train_image_ids, validation_image_ids = [], []
    for image_id, image_path, label_path in image_ids:
        with rasterio.open(image_path) as src:
            if src.count < 3:
                raise ValueError(f"Expected RGB imagery with >=3 bands: {image_path}")
            image = src.read((1, 2, 3))
            if src.crs is None:
                raise ValueError(f"Image has no CRS: {image_path}")
            labels = gpd.read_file(label_path)
            if labels.crs is None:
                raise ValueError(f"Label GeoJSON has no CRS: {label_path}")
            labels = labels.to_crs(src.crs)
            shapes = [(geom, 1) for geom in labels.geometry if geom is not None and not geom.is_empty]
            mask = rasterize(
                shapes,
                out_shape=(src.height, src.width),
                transform=src.transform,
                fill=0,
                dtype="uint8",
                all_touched=False,
            )

        split = "validation" if image_id in validation_ids else "train"
        (validation_image_ids if split == "validation" else train_image_ids).append(image_id)
        image_out = output_dir / "images" / split
        mask_out = output_dir / "masks" / split
        image_out.mkdir(parents=True, exist_ok=True)
        mask_out.mkdir(parents=True, exist_ok=True)
        rows, cols = image.shape[1:]
        for y in _windows(rows, tile_size, stride):
            for x in _windows(cols, tile_size, stride):
                image_tile = image[:, y:y + tile_size, x:x + tile_size]
                mask_tile = mask[y:y + tile_size, x:x + tile_size]
                if image_tile.shape[1:] != (tile_size, tile_size):
                    padded = np.zeros((3, tile_size, tile_size), dtype=image.dtype)
                    padded[:, :image_tile.shape[1], :image_tile.shape[2]] = image_tile
                    image_tile = padded
                    padded_mask = np.zeros((tile_size, tile_size), dtype=mask.dtype)
                    padded_mask[:mask_tile.shape[0], :mask_tile.shape[1]] = mask_tile
                    mask_tile = padded_mask
                image_tile = np.clip(
                    (image_tile.astype(np.float32) - lower[:, None, None])
                    / (upper - lower)[:, None, None] * 255.0,
                    0.0,
                    255.0,
                ).astype(np.uint8)
                positive = bool(mask_tile.any())
                if split == "train" and not positive and rng.random() > negative_keep_fraction:
                    continue
                stem = f"{image_id}_{y}_{x}"
                np.save(image_out / f"{stem}.npy", image_tile)
                np.save(mask_out / f"{stem}.npy", mask_tile)
                counts["tiles"] += 1
                counts["positive_tiles" if positive else "negative_tiles"] += 1

    manifest = {
        "source": "SpaceNet 2 AOI 2 Vegas RGB-PanSharpen images and building GeoJSON labels",
        "tile_size": tile_size,
        "stride": stride,
        "validation_fraction_by_source_image": validation_fraction,
        "negative_train_tile_keep_fraction": negative_keep_fraction,
        "seed": seed,
        "rgb_normalization": {
            "method": "per-band median of source-image 2nd and 98th percentiles over training images",
            "lower": lower.tolist(),
            "upper": upper.tolist(),
            "stored_pixel_range": [0, 255],
        },
        "train_source_image_ids": sorted(train_image_ids),
        "validation_source_image_ids": sorted(validation_ids),
        "counts": counts,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="SpaceNet RGB-PanSharpen image folder")
    parser.add_argument("--labels", type=Path, required=True, help="SpaceNet buildings GeoJSON folder")
    parser.add_argument("--output", type=Path, default=Path("data/spacenet_tiles"))
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--stride", type=int, default=256)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--negative-keep-fraction", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    manifest = prepare(
        args.images, args.labels, args.output,
        tile_size=args.tile_size, stride=args.stride,
        validation_fraction=args.validation_fraction,
        negative_keep_fraction=args.negative_keep_fraction, seed=args.seed,
    )
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
