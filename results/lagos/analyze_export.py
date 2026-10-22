"""Reproducibly audit the exported Lagos Open Buildings GeoJSON and summary CSV."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import PIL
import shapely
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape
from shapely.prepared import prep


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent
PRESENTATION_DIR = ROOT / "results" / "presentation"
GEOJSON_PATH = DATA_DIR / "Ikeja_open_buildings_conf075.geojson"
SUMMARY_PATH = DATA_DIR / "Ikeja_open_buildings_conf075_summary.csv"
BOUNDARY_PATH = DATA_DIR / "Ikeja_boundary_gaul2025.geojson"
REPORT_PATH = DATA_DIR / "QA_REPORT.md"
SUMMARY_OUTPUT_PATH = DATA_DIR / "qa_summary.json"
LOG_PATH = DATA_DIR / "qa_run.log"

CANVAS = "#F6F8F6"
INK = "#132824"
MUTED = "#52635E"
GRID = "#D9E2DE"
GREEN = "#07866B"
PALE_GREEN = "#BFE4D7"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2") / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def read_summary(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError(f"Expected one summary record; found {len(rows)}.")
    return rows[0]


def polygon_rings(geometry: dict[str, Any]) -> Iterable[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon":
        yield from coordinates or []
    elif kind == "MultiPolygon":
        for polygon in coordinates or []:
            yield from polygon
    else:
        raise ValueError(f"Unsupported geometry type {kind!r}.")


def check_ring(ring: list[list[float]]) -> tuple[bool, int, float, float, float, float]:
    if not isinstance(ring, list) or len(ring) < 4:
        return False, 0, math.inf, -math.inf, math.inf, -math.inf
    coordinates: list[tuple[float, float]] = []
    for coordinate in ring:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            return False, 0, math.inf, -math.inf, math.inf, -math.inf
        lon, lat = coordinate[0], coordinate[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            return False, 0, math.inf, -math.inf, math.inf, -math.inf
        if not math.isfinite(lon) or not math.isfinite(lat):
            return False, 0, math.inf, -math.inf, math.inf, -math.inf
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            return False, 0, math.inf, -math.inf, math.inf, -math.inf
        coordinates.append((float(lon), float(lat)))
    closed = coordinates[0] == coordinates[-1]
    return (
        closed,
        len(coordinates),
        min(point[0] for point in coordinates),
        max(point[0] for point in coordinates),
        min(point[1] for point in coordinates),
        max(point[1] for point in coordinates),
    )


def draw_map(
    features: list[dict[str, Any]], extent: list[float], path: Path, name: str, count: int,
    task_started: str, threshold: float, boundary_geometry: dict[str, Any] | None,
) -> None:
    width, height = 2200, 1580
    image = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(image)
    draw.text((105, 58), f"Building footprints | {name} LGA", fill=INK, font=font(58, True))
    draw.text((108, 132), f"{count:,} clipped Open Buildings features  •  confidence ≥ {threshold:.2f}", fill=MUTED, font=font(30))

    lon_min, lon_max, lat_min, lat_max = extent
    if boundary_geometry:
        boundary_minx, boundary_miny, boundary_maxx, boundary_maxy = shape(boundary_geometry).bounds
        lon_min = min(lon_min, boundary_minx)
        lon_max = max(lon_max, boundary_maxx)
        lat_min = min(lat_min, boundary_miny)
        lat_max = max(lat_max, boundary_maxy)
    lon_pad = max((lon_max - lon_min) * 0.04, 0.001)
    lat_pad = max((lat_max - lat_min) * 0.04, 0.001)
    lon_min, lon_max = lon_min - lon_pad, lon_max + lon_pad
    lat_min, lat_max = lat_min - lat_pad, lat_max + lat_pad
    mean_lat = (lat_min + lat_max) / 2
    cos_lat = math.cos(math.radians(mean_lat))

    left, top, right, bottom = 180, 235, 1840, 1330
    px_per_degree = min(
        (right - left) / ((lon_max - lon_min) * cos_lat),
        (bottom - top) / (lat_max - lat_min),
    )

    def project(lon: float, lat: float) -> tuple[float, float]:
        x = left + (lon - lon_min) * cos_lat * px_per_degree
        y = top + (lat_max - lat) * px_per_degree
        return x, y

    # Graticule in geographic coordinates; the map uses an equirectangular
    # local approximation with longitude scaled by cos(latitude).
    lon_step = 0.02
    lat_step = 0.02
    x = math.floor(lon_min / lon_step) * lon_step
    while x <= lon_max:
        px, _ = project(x, mean_lat)
        if left <= px <= right:
            draw.line((px, top, px, bottom), fill=GRID, width=2)
            draw.text((px - 42, bottom + 18), f"{x:.2f}°E", fill=MUTED, font=font(23))
        x += lon_step
    y = math.floor(lat_min / lat_step) * lat_step
    while y <= lat_max:
        _, py = project(lon_min, y)
        if top <= py <= bottom:
            draw.line((left, py, right, py), fill=GRID, width=2)
            draw.text((35, py - 15), f"{y:.2f}°N", fill=MUTED, font=font(23))
        y += lat_step

    for feature in features:
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        polygons = [geometry.get("coordinates", [])] if kind == "Polygon" else geometry.get("coordinates", [])
        for polygon in polygons:
            if not polygon:
                continue
            outer = [project(float(p[0]), float(p[1])) for p in polygon[0]]
            if len(outer) >= 4:
                draw.polygon(outer, fill=GREEN, outline=CANVAS, width=1)
            # Render interior rings as holes when present.
            for hole in polygon[1:]:
                hole_points = [project(float(p[0]), float(p[1])) for p in hole]
                if len(hole_points) >= 4:
                    draw.polygon(hole_points, fill=CANVAS)

    draw.rectangle((left, top, right, bottom), outline="#81928C", width=2)
    draw.text((left, bottom + 65), "Longitude", fill=MUTED, font=font(24, True))
    draw.text((32, top - 43), "Latitude", fill=MUTED, font=font(24, True))

    # North arrow.
    ax, ay = right - 36, top + 85
    draw.line((ax, ay + 65, ax, ay), fill=INK, width=6)
    draw.polygon([(ax, ay - 2), (ax - 19, ay + 32), (ax + 19, ay + 32)], fill=INK)
    draw.text((ax - 14, ay + 72), "N", fill=INK, font=font(26, True))

    # One kilometre scale bar using local latitude conversion.
    km_pixels = px_per_degree / 111.32
    sx, sy = left + 45, bottom - 52
    draw.line((sx, sy, sx + km_pixels, sy), fill=INK, width=8)
    draw.line((sx, sy - 11, sx, sy + 11), fill=INK, width=4)
    draw.line((sx + km_pixels, sy - 11, sx + km_pixels, sy + 11), fill=INK, width=4)
    draw.text((sx, sy - 43), "1 km", fill=INK, font=font(23, True))

    if boundary_geometry:
        kind = boundary_geometry.get("type")
        coordinates = boundary_geometry.get("coordinates", [])
        polygons = [coordinates] if kind == "Polygon" else coordinates
        for polygon in polygons:
            if polygon:
                ring = [project(float(p[0]), float(p[1])) for p in polygon[0]]
                if len(ring) >= 4:
                    draw.line(ring, fill=INK, width=5, joint="curve")
        boundary_note = "GAUL 2025 boundary outline is shown; export features are clipped to this boundary."
    else:
        boundary_note = "The boundary file was not supplied; map frame follows the exported feature extent only."
    date_text = task_started[:10] if task_started else "date not recorded"
    draw.text((105, 1452), f"Source: Google Research Open Buildings V3; Earth Engine task started {date_text}.", fill=MUTED, font=font(22))
    draw.text((105, 1490), boundary_note, fill=MUTED, font=font(19))
    image.save(path, format="PNG", optimize=True)


def draw_bars(
    title: str, subtitle: str, labels: list[str], values: list[int], path: Path,
    footer: str = "Count of features in each confidence interval.",
) -> None:
    width, height = 1800, 1050
    image = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(image)
    draw.text((95, 58), title, fill=INK, font=font(52, True))
    draw.text((98, 128), subtitle, fill=MUTED, font=font(26))
    left, top, right, bottom = 170, 230, 1660, 820
    maximum = max(values) * 1.15
    for tick in range(0, 6):
        value = maximum * tick / 5
        y = bottom - (bottom - top) * tick / 5
        draw.line((left, y, right, y), fill=GRID, width=2)
        draw.text((45, y - 15), f"{value:,.0f}", fill=MUTED, font=font(20))
    gap = 30
    bar_width = (right - left - gap * (len(values) - 1)) / len(values)
    for i, (label, value) in enumerate(zip(labels, values)):
        x0 = left + i * (bar_width + gap)
        x1 = x0 + bar_width
        y1 = bottom - (bottom - top) * value / maximum
        draw.rectangle((x0, y1, x1, bottom), fill=GREEN)
        draw.text((x0, y1 - 38), f"{value:,}", fill=INK, font=font(22, True))
        draw.text((x0 + 2, bottom + 22), label, fill=MUTED, font=font(23))
    draw.line((left, bottom, right, bottom), fill=INK, width=2)
    draw.text((left, 900), footer, fill=MUTED, font=font(22))
    image.save(path, format="PNG", optimize=True)


def draw_area_histogram(areas: list[float], path: Path) -> None:
    bins = [0, 25, 50, 100, 250, 500, 1000, 2500, 5000, math.inf]
    labels = ["<25", "25–50", "50–100", "100–250", "250–500", "500–1k", "1k–2.5k", "2.5k–5k", ">5k"]
    counts = [sum(bins[i] <= value < bins[i + 1] for value in areas) for i in range(len(labels))]
    draw_bars(
        "Clipped footprint area", "Distribution by area class (m²)", labels, counts, path,
        footer="Feature count in each clipped-area class; areas are in square metres.",
    )


def confidence_distribution(values: list[float], threshold: float) -> dict[str, int]:
    """Count scores in five percentage-point bins from the actual cutoff to 1.0."""
    if not 0 <= threshold <= 1:
        raise ValueError("minimum_confidence must be between 0 and 1.")
    if threshold == 1:
        return {"1.00": sum(score == 1.0 for score in values)}
    boundaries = [threshold]
    next_boundary = math.ceil((threshold - 1e-12) / 0.05) * 0.05
    next_boundary = round(next_boundary, 2)
    if next_boundary <= threshold + 1e-9:
        next_boundary = round(next_boundary + 0.05, 2)
    while next_boundary < 1 - 1e-9:
        boundaries.append(next_boundary)
        next_boundary = round(next_boundary + 0.05, 2)
    boundaries.append(1.0)
    bins: dict[str, int] = {}
    for index, (lower, upper) in enumerate(zip(boundaries, boundaries[1:])):
        label = f"{lower:.2f}–{upper:.2f}"
        bins[label] = sum(
            lower <= score < upper or (index == len(boundaries) - 2 and score == 1.0)
            for score in values
        )
    return bins


def main(argv: list[str] | None = None) -> int:
    global GEOJSON_PATH, SUMMARY_PATH, BOUNDARY_PATH, PRESENTATION_DIR
    global REPORT_PATH, SUMMARY_OUTPUT_PATH, LOG_PATH

    parser = argparse.ArgumentParser(
        description="Validate a Lagos Open Buildings export and rebuild its report and figures."
    )
    parser.add_argument("--geojson", type=Path, default=GEOJSON_PATH, help="Footprint GeoJSON path.")
    parser.add_argument("--summary-csv", type=Path, default=SUMMARY_PATH, help="Earth Engine summary CSV path.")
    parser.add_argument("--boundary-geojson", type=Path, default=None, help="Optional matching exported LGA boundary.")
    parser.add_argument("--presentation-dir", type=Path, default=PRESENTATION_DIR, help="Directory for generated figures.")
    parser.add_argument("--report", type=Path, default=None, help="Optional QA report output path.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional machine-readable summary path.")
    parser.add_argument("--log", type=Path, default=None, help="Optional run log path.")
    args = parser.parse_args(argv)
    GEOJSON_PATH = args.geojson.resolve()
    SUMMARY_PATH = args.summary_csv.resolve()
    PRESENTATION_DIR = args.presentation_dir.resolve()
    if not GEOJSON_PATH.exists() or not SUMMARY_PATH.exists():
        print(f"ERROR: input file not found: {GEOJSON_PATH if not GEOJSON_PATH.exists() else SUMMARY_PATH}")
        return 2
    meta = read_summary(SUMMARY_PATH)
    area_name = meta["boundary_name"].strip()
    slug = re.sub(r"[^a-z0-9]+", "_", area_name.lower()).strip("_") or "lagos_area"
    default_boundary = SUMMARY_PATH.parent / f"{area_name}_boundary_gaul2025.geojson"
    BOUNDARY_PATH = args.boundary_geojson.resolve() if args.boundary_geojson else default_boundary
    if args.boundary_geojson and not BOUNDARY_PATH.exists():
        raise FileNotFoundError(f"Requested boundary GeoJSON does not exist: {BOUNDARY_PATH}")
    REPORT_PATH = args.report.resolve() if args.report else (
        DATA_DIR / "QA_REPORT.md" if slug == "ikeja" else SUMMARY_PATH.parent / f"{slug}_QA_REPORT.md"
    )
    SUMMARY_OUTPUT_PATH = args.summary_json.resolve() if args.summary_json else (
        DATA_DIR / "qa_summary.json" if slug == "ikeja" else SUMMARY_PATH.parent / f"{slug}_qa_summary.json"
    )
    LOG_PATH = args.log.resolve() if args.log else (
        DATA_DIR / "qa_run.log" if slug == "ikeja" else SUMMARY_PATH.parent / f"{slug}_qa_run.log"
    )
    figure_prefix = "" if slug == "ikeja" else f"{slug}_"
    PRESENTATION_DIR.mkdir(parents=True, exist_ok=True)
    with GEOJSON_PATH.open(encoding="utf-8") as stream:
        collection = json.load(stream)
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Input is not a GeoJSON FeatureCollection.")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON FeatureCollection has no feature list.")

    threshold = float(meta["minimum_confidence"])
    expected_count = int(meta["filtered_footprint_count"])
    boundary_area_km2 = float(meta["boundary_area_km2"])
    if not 0 <= threshold <= 1 or boundary_area_km2 <= 0:
        raise ValueError("Summary CSV must contain a confidence cutoff in [0, 1] and a positive boundary area.")
    boundary_collection = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8")) if BOUNDARY_PATH.exists() else None
    boundary_geometry = None
    prepared_boundary = None
    if boundary_collection:
        boundary_features = boundary_collection.get("features", [])
        if len(boundary_features) != 1:
            raise ValueError(f"Expected one boundary feature; found {len(boundary_features)}.")
        boundary_geometry = boundary_features[0].get("geometry")
        if not boundary_geometry:
            raise ValueError("Boundary GeoJSON has an empty geometry.")
        boundary_shape = shape(boundary_geometry)
        if boundary_shape.is_empty or not boundary_shape.is_valid:
            raise ValueError("Boundary geometry is empty or topologically invalid.")
        prepared_boundary = prep(boundary_shape)
    confidences: list[float] = []
    areas: list[float] = []
    ids: list[str] = []
    geometry_types: Counter[str] = Counter()
    closed_rings = 0
    open_rings = 0
    invalid_rings = 0
    finite_coordinates = True
    extent = [math.inf, -math.inf, math.inf, -math.inf]
    missing_confidence = 0
    missing_area = 0
    empty_geometry = 0
    invalid_topology = 0
    outside_boundary = 0
    missing_ids = 0

    for feature in features:
        feature_id = feature.get("id")
        if feature_id is None or str(feature_id).strip() == "":
            missing_ids += 1
        else:
            ids.append(str(feature_id))
        geometry = feature.get("geometry") or {}
        geometry_types[str(geometry.get("type"))] += 1
        if not geometry.get("coordinates"):
            empty_geometry += 1
        try:
            geom_shape = shape(geometry)
            if geom_shape.is_empty or not geom_shape.is_valid or geom_shape.area <= 0:
                invalid_topology += 1
            if prepared_boundary is not None and not prepared_boundary.covers(geom_shape):
                outside_boundary += 1
        except Exception:
            invalid_topology += 1
        properties = feature.get("properties") or {}
        confidence = properties.get("confidence")
        area = properties.get("clipped_area_m2")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(confidence):
            confidences.append(float(confidence))
        else:
            missing_confidence += 1
        if isinstance(area, (int, float)) and not isinstance(area, bool) and math.isfinite(area):
            areas.append(float(area))
        else:
            missing_area += 1

        try:
            rings = list(polygon_rings(geometry))
        except (TypeError, ValueError):
            rings = []
            invalid_rings += 1
        for ring in rings:
            valid, _, xmin, xmax, ymin, ymax = check_ring(ring)
            if valid:
                closed_rings += 1
                extent[0] = min(extent[0], xmin)
                extent[1] = max(extent[1], xmax)
                extent[2] = min(extent[2], ymin)
                extent[3] = max(extent[3], ymax)
            else:
                open_rings += 1
                invalid_rings += 1
                finite_coordinates = False

    count = len(features)
    unique_ids = len(set(ids))
    min_conf = min(confidences) if confidences else None
    max_conf = max(confidences) if confidences else None
    mean_conf = statistics.fmean(confidences) if confidences else None
    median_conf = statistics.median(confidences) if confidences else None
    area_sum = math.fsum(areas)
    sorted_areas = sorted(areas)
    percentile = lambda p: sorted_areas[round((len(sorted_areas) - 1) * p)] if sorted_areas else None
    confidence_bins = confidence_distribution(confidences, threshold)
    checks = {
        "geojson_feature_count_matches_summary_csv": count == expected_count,
        "all_confidence_values_meet_minimum": len(confidences) == count and bool(confidences) and min_conf >= threshold,
        "confidence_scores_within_unit_interval": len(confidences) == count and all(0 <= value <= 1 for value in confidences),
        "all_clipped_areas_are_positive": len(areas) == count and all(value > 0 for value in areas),
        "unique_feature_ids": unique_ids == count and missing_ids == 0,
        "polygon_rings_closed_and_coordinates_wgs84": invalid_rings == 0 and finite_coordinates,
        "feature_geometries_present": empty_geometry == 0,
        "polygon_topology_valid": invalid_topology == 0,
        "inside_matching_boundary": (outside_boundary == 0) if prepared_boundary is not None else "NOT RUN — matching GAUL 2025 boundary GeoJSON was not supplied",
    }

    output = {
        "analysis_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_environment": {
            "python": sys.version.split()[0],
            "pillow": PIL.__version__,
            "shapely": shapely.__version__,
        },
        "inputs": {
            "geojson": {"path": GEOJSON_PATH.name, "bytes": GEOJSON_PATH.stat().st_size, "sha256": sha256(GEOJSON_PATH)},
            "summary_csv": {"path": SUMMARY_PATH.name, "bytes": SUMMARY_PATH.stat().st_size, "sha256": sha256(SUMMARY_PATH)},
        },
        "source_metadata": meta,
        "feature_count": count,
        "feature_count_density_per_km2": count / boundary_area_km2,
        "feature_density_note": "Descriptive prediction count per exported boundary area; not population density or completeness.",
        "geometry_types": dict(geometry_types),
        "coordinate_extent_lonlat": extent,
        "confidence": {
            "minimum": min_conf,
            "maximum": max_conf,
            "mean": mean_conf,
            "median": median_conf,
            "threshold": threshold,
            "bins": confidence_bins,
            "bin_percentages": {
                label: round(value / count * 100, 2) if count else 0
                for label, value in confidence_bins.items()
            },
        },
        "clipped_area_m2": {
            "sum_non_dissolved_features": area_sum,
            "median": statistics.median(areas) if areas else None,
            "p90": percentile(0.90),
            "maximum": max(areas) if areas else None,
            "summed_feature_area_over_boundary_area_percent": area_sum / (boundary_area_km2 * 1_000_000) * 100,
            "note": "Summed feature areas are not a dissolved coverage measure; overlaps are not removed.",
        },
        "quality_checks": checks,
        "geometry_structure": {
            "closed_rings": closed_rings,
            "open_or_invalid_rings": open_rings,
            "empty_geometries": empty_geometry,
            "missing_confidence": missing_confidence,
            "missing_clipped_area": missing_area,
            "missing_feature_ids": missing_ids,
            "invalid_topology": invalid_topology,
            "outside_boundary_features": outside_boundary if prepared_boundary is not None else None,
        },
        "independent_boundary_validation": "Exact geometry containment checked against the matching exported boundary." if prepared_boundary is not None else "Not possible from the supplied files; rerun the updated notebook and add its matching boundary GeoJSON.",
    }
    if BOUNDARY_PATH.exists():
        output["inputs"]["boundary_geojson"] = {
            "path": BOUNDARY_PATH.name,
            "bytes": BOUNDARY_PATH.stat().st_size,
            "sha256": sha256(BOUNDARY_PATH),
        }
    SUMMARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_lines = [
        f"# {area_name} Open Buildings export: data quality report",
        "",
        f"Analysis run (UTC): {output['analysis_timestamp_utc']}",
        f"Runtime: Python {sys.version.split()[0]}, Pillow {PIL.__version__}, Shapely {shapely.__version__}.",
        f"Boundary: {meta['boundary_name']} LGA; {boundary_area_km2:.3f} km² per the supplied summary CSV.",
        f"Source: {meta['footprint_dataset']} (inference year {meta['source_inference_year']}); confidence cutoff {threshold:.2f}.",
        "",
        "## Results",
        "",
        f"- Exported features: **{count:,}** (CSV reports {expected_count:,}).",
        f"- Prediction density: {count / boundary_area_km2:,.1f} features per km² of reported boundary area; this is not population density or a completeness estimate.",
        f"- Geometry types: {', '.join(f'{k}: {v:,}' for k, v in sorted(geometry_types.items()))}.",
        f"- Confidence: mean {mean_conf:.4f}; median {median_conf:.4f}; range {min_conf:.4f}–{max_conf:.4f}.",
        f"- Confidence distribution: {', '.join(f'{k}: {v:,}' for k, v in confidence_bins.items())}.",
        f"- Clipped feature area: median {statistics.median(areas):,.1f} m²; 90th percentile {percentile(0.90):,.1f} m²; maximum {max(areas):,.1f} m².",
        f"- Sum of per-feature clipped areas: {area_sum / 1_000_000:.3f} km². This is a non-dissolved sum and is not an area-coverage estimate.",
        f"- Exported coordinate extent: {extent[0]:.6f}–{extent[1]:.6f}°E, {extent[2]:.6f}–{extent[3]:.6f}°N.",
        "",
        "## Checks",
        "",
    ]
    for check, result in checks.items():
        if isinstance(result, bool):
            report_lines.append(f"- {'PASS' if result else 'FAIL'} — {check.replace('_', ' ')}.")
        else:
            report_lines.append(f"- **NOT VERIFIED** — {result}.")
    report_lines.extend([
        "",
        output["independent_boundary_validation"],
        "",
        "## Reproduction",
        "",
        "From the repository root, install the analysis dependencies and rerun:",
        "",
        "```powershell",
        "python -m pip install -r results/lagos/requirements-analysis.txt",
        "python results/lagos/analyze_export.py",
        "```",
        "",
        "For a different Lagos LGA, pass its matching inputs explicitly:",
        "",
        "```powershell",
        "python results/lagos/analyze_export.py --geojson results/lagos/<LGA>_open_buildings_conf075.geojson --summary-csv results/lagos/<LGA>_open_buildings_conf075_summary.csv --boundary-geojson results/lagos/<LGA>_boundary_gaul2025.geojson",
        "```",
        "",
        f"SHA-256 GeoJSON: `{sha256(GEOJSON_PATH)}`  ",
        f"SHA-256 summary CSV: `{sha256(SUMMARY_PATH)}`",
        "",
    ])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")

    log_lines = [
        f"Analysis UTC: {output['analysis_timestamp_utc']}",
        f"Python: {sys.version.split()[0]}",
        f"Pillow: {PIL.__version__}; Shapely: {shapely.__version__}",
        f"GeoJSON: {GEOJSON_PATH.name} ({GEOJSON_PATH.stat().st_size} bytes)",
        f"GeoJSON SHA-256: {sha256(GEOJSON_PATH)}",
        f"Summary CSV SHA-256: {sha256(SUMMARY_PATH)}",
        f"Features: {count} (summary count: {expected_count})",
        f"Minimum confidence: {min_conf} (required: {threshold})",
        f"Positive clipped areas: {len(areas)}/{count}",
        f"Valid closed rings: {closed_rings}; invalid/open: {open_rings}",
        f"Independent boundary containment: {'PASS' if prepared_boundary is not None and outside_boundary == 0 else 'FAIL' if prepared_boundary is not None else 'NOT VERIFIED (boundary polygon absent).'}",
    ]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    confidence_labels = list(confidence_bins)
    confidence_counts = list(confidence_bins.values())
    draw_map(features, extent, PRESENTATION_DIR / f"{slug}_footprints_overview.png", area_name, count, meta.get("export_started_utc", ""), threshold, boundary_geometry)
    draw_bars(
        f"{area_name} Open Buildings confidence scores",
        f"{area_name} export • all {count:,} retained features • minimum score {threshold:.2f}",
        confidence_labels,
        confidence_counts,
        PRESENTATION_DIR / f"{figure_prefix}confidence_distribution.png",
    )
    draw_area_histogram(areas, PRESENTATION_DIR / f"{figure_prefix}footprint_area_distribution.png")

    failures = [key for key, value in checks.items() if isinstance(value, bool) and not value]
    for key, value in checks.items():
        print(f"{'PASS' if value is True else 'INFO' if not isinstance(value, bool) else 'FAIL'}: {key}")
    print(f"Features: {count:,}; mean confidence: {mean_conf:.4f}; sum of clipped feature area: {area_sum/1_000_000:.3f} km².")
    print(f"Report: {REPORT_PATH}")
    print(f"Summary: {SUMMARY_OUTPUT_PATH}")
    print(f"Figures: {PRESENTATION_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
