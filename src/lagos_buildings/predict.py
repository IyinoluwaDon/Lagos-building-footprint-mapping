"""Apply a trained U-Net to one georeferenced Lagos RGB image tile."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import torch
from pyproj import CRS as PyprojCRS
from rasterio.features import rasterize, shapes
from shapely.geometry import shape
from shapely.ops import unary_union

from lagos_buildings.model import UNet
from lagos_buildings.prepare import _windows


def _boundary(path: Path, target_crs):
    boundary = gpd.read_file(path)
    if boundary.crs is None:
        raise ValueError(f"Boundary has no coordinate reference system: {path}")
    boundary = boundary.to_crs(target_crs)
    geometry = unary_union([geom for geom in boundary.geometry if geom is not None and not geom.is_empty])
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Lagos boundary is empty or invalid.")
    return geometry


def predict_tile(
    checkpoint_path: Path,
    image_path: Path,
    boundary_path: Path,
    output_raster: Path,
    output_geojson: Path,
    *,
    stride: int = 128,
    batch_size: int = 8,
) -> dict:
    if stride <= 0 or batch_size <= 0:
        raise ValueError("stride and batch_size must be positive integers.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model = UNet(
        in_channels=int(checkpoint["in_channels"]),
        base_channels=int(checkpoint["base_channels"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    tile_size = int(checkpoint["tile_size"])
    if stride > tile_size:
        raise ValueError("stride must not exceed the model tile size.")
    image_scale = float(checkpoint["image_scale"])
    image_lower = np.asarray(checkpoint["image_lower"], dtype=np.float32)[:, None, None]
    image_upper = np.asarray(checkpoint["image_upper"], dtype=np.float32)[:, None, None]
    threshold = float(checkpoint["threshold"])

    with rasterio.open(image_path) as src:
        if src.crs is None:
            raise ValueError(f"Lagos image has no CRS: {image_path}")
        if not src.crs.is_projected:
            raise ValueError("Lagos inference image must use a projected CRS with linear pixel units.")
        if src.count < 3:
            raise ValueError("Lagos inference image must have at least three RGB bands.")
        axis_info = PyprojCRS.from_user_input(src.crs).axis_info
        if len(axis_info) < 2 or any(axis.unit_conversion_factor is None for axis in axis_info[:2]):
            raise ValueError("Could not determine projected CRS units for the Lagos image.")
        resolution_m = [abs(src.res[index]) * axis_info[index].unit_conversion_factor for index in range(2)]
        if max(resolution_m) > 1.0:
            raise ValueError(
                f"Expected high-resolution imagery compatible with SpaceNet RGB (~0.3 m pixels); got {resolution_m} m pixels."
            )
        boundary = _boundary(boundary_path, src.crs)
        boundary_mask = rasterize(
            [(boundary, 1)], out_shape=(src.height, src.width), transform=src.transform,
            fill=0, dtype="uint8", all_touched=False,
        ).astype(bool)
        valid_mask = src.dataset_mask() > 0
        region_mask = boundary_mask & valid_mask
        if not region_mask.any():
            raise ValueError("The supplied Lagos boundary does not intersect valid pixels in the image.")

        probability_sum = np.zeros((src.height, src.width), dtype=np.float32)
        weight_sum = np.zeros((src.height, src.width), dtype=np.uint16)
        batch, locations = [], []

        def infer_pending() -> None:
            if not batch:
                return
            tensor = torch.from_numpy(np.stack(batch)).to(device)
            with torch.no_grad():
                probs = torch.sigmoid(model(tensor)).cpu().numpy()[:, 0]
            for probability, (y, x, height, width) in zip(probs, locations):
                probability_sum[y:y + height, x:x + width] += probability[:height, :width]
                weight_sum[y:y + height, x:x + width] += 1
            batch.clear()
            locations.clear()

        for y in _windows(src.height, tile_size, stride):
            for x in _windows(src.width, tile_size, stride):
                height = min(tile_size, src.height - y)
                width = min(tile_size, src.width - x)
                window = rasterio.windows.Window(x, y, width, height)
                rgb = src.read((1, 2, 3), window=window, boundless=True, fill_value=0).astype(np.float32)
                if rgb.shape[1:] != (tile_size, tile_size):
                    padded = np.zeros((3, tile_size, tile_size), dtype=np.float32)
                    padded[:, :height, :width] = rgb[:, :height, :width]
                    rgb = padded
                scaled = (rgb - image_lower) / (image_upper - image_lower) * image_scale
                batch.append(np.clip(scaled / image_scale, 0.0, 1.0))
                locations.append((y, x, height, width))
                if len(batch) >= batch_size:
                    infer_pending()
        infer_pending()

        denominator = np.maximum(weight_sum, 1)
        probability = probability_sum / denominator
        probability[~region_mask] = -9999.0
        binary = (probability >= threshold) & region_mask
        output_raster.parent.mkdir(parents=True, exist_ok=True)
        output_geojson.parent.mkdir(parents=True, exist_ok=True)
        raster_profile = src.profile.copy()
        raster_profile.update(count=1, dtype="float32", nodata=-9999.0, compress="deflate")
        with rasterio.open(output_raster, "w", **raster_profile) as dst:
            dst.write(probability.astype(np.float32), 1)

        features = []
        for geometry_data, value in shapes(binary.astype(np.uint8), mask=binary, transform=src.transform):
            if value != 1:
                continue
            polygon = shape(geometry_data).intersection(boundary)
            if polygon.is_empty:
                continue
            features.append({"geometry": polygon, "properties": {"class": "building", "source": "spacenet_unet"}})
        if features:
            result = gpd.GeoDataFrame.from_features(features, crs=src.crs).to_crs("EPSG:4326")
            result.to_file(output_geojson, driver="GeoJSON")
        else:
            output_geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    return {
        "checkpoint": str(checkpoint_path),
        "image": str(image_path),
        "boundary": str(boundary_path),
        "output_raster": str(output_raster),
        "output_geojson": str(output_geojson),
        "threshold": threshold,
        "predicted_building_polygons": len(features),
        "device": str(device),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("outputs/unet_spacenet2_vegas.pt"))
    parser.add_argument("--image", type=Path, required=True, help="High-resolution georeferenced Lagos RGB GeoTIFF tile")
    parser.add_argument("--boundary", type=Path, required=True, help="Lagos boundary GeoJSON")
    parser.add_argument("--output-raster", type=Path, required=True, help="Probability GeoTIFF path")
    parser.add_argument("--output-geojson", type=Path, required=True, help="Clipped building polygon GeoJSON path")
    parser.add_argument("--stride", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    import json
    print(json.dumps(predict_tile(
        args.checkpoint, args.image, args.boundary, args.output_raster, args.output_geojson,
        stride=args.stride, batch_size=args.batch_size,
    ), indent=2))


if __name__ == "__main__":
    main()
