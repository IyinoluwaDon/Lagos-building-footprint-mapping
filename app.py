"""Interactive, local-first dashboard for Lagos Open Buildings exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st
import altair as alt


ROOT = Path(__file__).resolve().parent
DEFAULT_GEOJSON = ROOT / "results" / "lagos" / "Ikeja_open_buildings_conf075.geojson"
DEFAULT_SUMMARY = ROOT / "results" / "lagos" / "Ikeja_open_buildings_conf075_summary.csv"
QA_SUMMARY = ROOT / "results" / "lagos" / "qa_summary.json"
MODEL_METRICS = ROOT / "outputs" / "unet_spacenet2_vegas.metrics.json"
MODEL_TEST_METRICS = ROOT / "outputs" / "unet_spacenet2_vegas.test_metrics.json"
MODEL_TEST_PREVIEW = ROOT / "outputs" / "model_test_scene291_preview.png"

st.set_page_config(
    page_title="Lagos Building Footprints",
    page_icon=":material/location_city:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _walk_coordinates(coordinates: Any) -> Iterator[tuple[float, float]]:
    """Yield valid longitude/latitude pairs from nested GeoJSON coordinates."""
    if isinstance(coordinates, (list, tuple)):
        if len(coordinates) >= 2 and all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates[:2]):
            yield float(coordinates[0]), float(coordinates[1])
            return
        for child in coordinates:
            yield from _walk_coordinates(child)


def _bbox_center(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = list(_walk_coordinates(geometry.get("coordinates")))
    if not coords:
        return None, None
    longitudes = [point[0] for point in coords]
    latitudes = [point[1] for point in coords]
    return (min(longitudes) + max(longitudes)) / 2, (min(latitudes) + max(latitudes)) / 2


def _parse_summary(raw: bytes) -> dict[str, str]:
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if len(rows) != 1:
        raise ValueError(f"Expected one summary CSV row; found {len(rows)}.")
    return rows[0]


@st.cache_data(show_spinner="Loading footprint export…", max_entries=4)
def load_export(geojson_bytes: bytes, summary_bytes: bytes) -> dict[str, Any]:
    parsed = json.loads(geojson_bytes)
    if parsed.get("type") != "FeatureCollection" or not isinstance(parsed.get("features"), list):
        raise ValueError("GeoJSON must be a FeatureCollection with a features array.")
    summary = _parse_summary(summary_bytes)
    rows: list[dict[str, Any]] = []
    features = parsed["features"]
    for position, feature in enumerate(features):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        lon, lat = _bbox_center(geometry)
        rows.append({
            "id": str(feature.get("id", props.get("system:index", position))),
            "confidence": _number(props.get("confidence")),
            "clipped_area_m2": _number(props.get("clipped_area_m2")),
            "geometry_type": geometry.get("type", "Missing"),
            "longitude": lon,
            "latitude": lat,
            "feature": feature,
        })
    confidence = [row["confidence"] for row in rows if row["confidence"] is not None]
    areas = [row["clipped_area_m2"] for row in rows if row["clipped_area_m2"] is not None]
    return {
        "geojson": parsed,
        "rows": rows,
        "summary": summary,
        "feature_count": len(features),
        "confidence": confidence,
        "areas": areas,
    }


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _float(summary: dict[str, str], key: str) -> float | None:
    return _number(summary.get(key))


def _fmt_number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def structural_checks(dataset: dict[str, Any]) -> list[dict[str, str]]:
    rows = dataset["rows"]
    ids = [row["id"] for row in rows]
    confidence = dataset["confidence"]
    areas = dataset["areas"]
    summary = dataset["summary"]
    reported_count = _float(summary, "filtered_footprint_count")
    floor = _float(summary, "minimum_confidence")
    return [
        {"Check": "Feature count matches export summary", "Result": "PASS" if reported_count == len(rows) else "CHECK", "Detail": f"{len(rows):,} features; summary reports {_fmt_number(reported_count)}."},
        {"Check": "Feature identifiers are unique", "Result": "PASS" if len(set(ids)) == len(ids) else "FAIL", "Detail": f"{len(ids) - len(set(ids)):,} duplicate identifiers."},
        {"Check": "Confidence values are present and within 0–1", "Result": "PASS" if len(confidence) == len(rows) and all(0 <= value <= 1 for value in confidence) else "FAIL", "Detail": f"{len(confidence):,} of {len(rows):,} features have valid confidence."},
        {"Check": "Confidence satisfies source cutoff", "Result": "PASS" if floor is not None and len(confidence) == len(rows) and all(value >= floor - 1e-9 for value in confidence) else "CHECK", "Detail": f"Source cutoff: {_fmt_number(floor, 2)}."},
        {"Check": "Clipped feature areas are positive", "Result": "PASS" if len(areas) == len(rows) and all(value > 0 for value in areas) else "FAIL", "Detail": f"{len(areas):,} of {len(rows):,} features have positive area."},
        {"Check": "Features use Polygon or MultiPolygon geometry", "Result": "PASS" if all(row["geometry_type"] in {"Polygon", "MultiPolygon"} for row in rows) else "FAIL", "Detail": "Expected footprint geometry types."},
        {"Check": "Exact boundary containment", "Result": "NOT RUN", "Detail": "Upload the matching GAUL boundary GeoJSON to enable this check."},
    ]


@st.cache_data(show_spinner="Checking all footprints against the uploaded boundary…", max_entries=2)
def verify_boundary(geojson_bytes: bytes, boundary_bytes: bytes) -> dict[str, Any]:
    """Run exact feature containment only when a user explicitly requests it."""
    from shapely.geometry import shape

    footprint_collection = json.loads(geojson_bytes)
    boundary_doc = json.loads(boundary_bytes)
    if boundary_doc.get("type") == "FeatureCollection":
        boundary_geometries = [shape(feature["geometry"]) for feature in boundary_doc["features"]]
    elif boundary_doc.get("type") == "Feature":
        boundary_geometries = [shape(boundary_doc["geometry"])]
    elif boundary_doc.get("type") in {"Polygon", "MultiPolygon"}:
        boundary_geometries = [shape(boundary_doc)]
    else:
        raise ValueError("Boundary must be a GeoJSON Feature, FeatureCollection, Polygon, or MultiPolygon.")
    boundary = boundary_geometries[0]
    for geometry in boundary_geometries[1:]:
        boundary = boundary.union(geometry)
    if boundary.is_empty or not boundary.is_valid:
        raise ValueError("Boundary geometry is empty or invalid.")
    contained = 0
    invalid = 0
    outside_ids: list[str] = []
    for index, feature in enumerate(footprint_collection["features"]):
        geometry_data = feature.get("geometry")
        try:
            geometry = shape(geometry_data) if geometry_data else None
            if geometry is None or geometry.is_empty or not geometry.is_valid:
                invalid += 1
                outside_ids.append(str(feature.get("id", index)))
            elif boundary.covers(geometry):
                contained += 1
            else:
                outside_ids.append(str(feature.get("id", index)))
        except (TypeError, ValueError):
            invalid += 1
            outside_ids.append(str(feature.get("id", index)))
    return {"contained": contained, "outside_or_invalid": len(outside_ids), "invalid_geometries": invalid, "total": len(footprint_collection["features"]), "outside_ids": outside_ids[:25]}


def _make_downloads(filtered_rows: list[dict[str, Any]], original: dict[str, Any]) -> tuple[bytes, bytes]:
    fc = {**original, "features": [row["feature"] for row in filtered_rows]}
    geojson_bytes = json.dumps(fc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    export_rows = [{key: value for key, value in row.items() if key != "feature"} for row in filtered_rows]
    return geojson_bytes, pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8")


def _save_interactive_outputs(
    directory: Path,
    safe_name: str,
    cutoff: float,
    geojson_bytes: bytes,
    csv_bytes: bytes,
    source_geojson: bytes,
    source_summary: bytes,
    selected_count: int,
) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    tag = f"conf{cutoff:.2f}"
    geojson_path = directory / f"{safe_name}_footprints_{tag}.geojson"
    csv_path = directory / f"{safe_name}_footprints_{tag}.csv"
    metadata_path = directory / f"{safe_name}_footprints_{tag}_run.json"
    geojson_path.write_bytes(geojson_bytes)
    csv_path.write_bytes(csv_bytes)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "area": safe_name,
        "interactive_confidence_cutoff": cutoff,
        "selected_feature_count": selected_count,
        "source_geojson_sha256": hashlib.sha256(source_geojson).hexdigest(),
        "source_summary_csv_sha256": hashlib.sha256(source_summary).hexdigest(),
        "output_geojson_sha256": hashlib.sha256(geojson_bytes).hexdigest(),
        "output_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "interpretation": "Subset of predictions already present in the source export; no new Earth Engine query was run.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return geojson_path, csv_path, metadata_path


def _render_map(rows: list[dict[str, Any]], boundary_bytes: bytes | None) -> None:
    coords = [{"longitude": row["longitude"], "latitude": row["latitude"], "confidence": row["confidence"], "area": row["clipped_area_m2"], "id": row["id"]} for row in rows if row["longitude"] is not None and row["latitude"] is not None]
    if not coords:
        st.info("No mappable coordinates were found in this selection.")
        return
    total_locations = len(coords)
    if len(coords) > 25000:
        stride = math.ceil(len(coords) / 25000)
        coords = coords[::stride]
    df = pd.DataFrame(coords)
    center_lon = float(df["longitude"].median())
    center_lat = float(df["latitude"].median())
    layers = [pdk.Layer(
        "ScatterplotLayer", data=df, get_position="[longitude, latitude]",
        get_fill_color="[22, 132, 105, 150]", get_line_color="[8, 74, 59, 190]",
        get_radius=17, radius_min_pixels=2, radius_max_pixels=6, line_width_min_pixels=0.5,
        pickable=True, auto_highlight=True,
    )]
    if boundary_bytes:
        try:
            boundary = json.loads(boundary_bytes)
            if boundary.get("type") == "FeatureCollection":
                layers.insert(0, pdk.Layer("GeoJsonLayer", data=boundary, stroked=True, filled=False, get_line_color=[20, 58, 120, 210], get_line_width=3, line_width_min_pixels=2, pickable=False))
            elif boundary.get("type") == "Feature":
                layers.insert(0, pdk.Layer("GeoJsonLayer", data=boundary, stroked=True, filled=False, get_line_color=[20, 58, 120, 210], get_line_width=3, line_width_min_pixels=2, pickable=False))
            else:
                st.warning("Boundary overlay expects a GeoJSON Feature or FeatureCollection.")
        except (ValueError, TypeError):
            st.warning("The boundary file could not be read as GeoJSON.")
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=11, pitch=0),
        tooltip={"html": "<b>Footprint</b> {id}<br/>Confidence: {confidence}<br/>Clipped area: {area} m²", "style": {"backgroundColor": "#123b34", "color": "white"}},
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )
    st.pydeck_chart(deck, width="stretch", height=570, alt="Map of predicted building footprint locations in the selected Lagos study area")
    st.caption(f"Showing {len(coords):,} of {total_locations:,} footprint locations at approximate bounding-box centers. A point represents a model prediction, not a verified building.")


def main() -> None:
    st.sidebar.markdown("## Lagos footprint explorer")
    st.sidebar.caption("Project 2 · Open Buildings V3")
    with st.sidebar.expander("Use another export", expanded=False):
        geojson_upload = st.file_uploader("Footprints GeoJSON", type=["geojson", "json"], key="footprints-upload")
        summary_upload = st.file_uploader("Matching summary CSV", type=["csv"], key="summary-upload")
        boundary_upload = st.file_uploader("Optional matching boundary GeoJSON", type=["geojson", "json"], key="boundary-upload")
        if (geojson_upload is None) != (summary_upload is None):
            st.warning("Upload both a footprints GeoJSON and its matching summary CSV. The supplied Ikeja export remains active.")
    if geojson_upload is not None and summary_upload is not None:
        geojson_bytes, summary_bytes = geojson_upload.getvalue(), summary_upload.getvalue()
        dataset_label = geojson_upload.name
    else:
        geojson_bytes, summary_bytes = DEFAULT_GEOJSON.read_bytes(), DEFAULT_SUMMARY.read_bytes()
        dataset_label = "Supplied Ikeja export"
    boundary_bytes = boundary_upload.getvalue() if boundary_upload is not None else None
    try:
        dataset = load_export(geojson_bytes, summary_bytes)
    except Exception as exc:
        st.error(f"Could not load the selected export: {exc}")
        st.stop()
    rows, summary = dataset["rows"], dataset["summary"]
    minimum_conf = _float(summary, "minimum_confidence") or 0.0
    observed_min = min(dataset["confidence"]) if dataset["confidence"] else minimum_conf
    observed_max = max(dataset["confidence"]) if dataset["confidence"] else 1.0
    slider_min = max(0.0, min(minimum_conf, observed_min))
    if slider_min >= observed_max:
        observed_max = min(1.0, slider_min + 0.001)
    default_cutoff = min(max(minimum_conf, slider_min), observed_max)
    cutoff = st.sidebar.slider("Minimum confidence to show", min_value=float(slider_min), max_value=float(observed_max), value=float(default_cutoff), step=0.01, help="Filters the predictions already present in this export. Lowering this below the export's original cutoff cannot recover footprints that were not exported.")
    filtered = [row for row in rows if row["confidence"] is not None and row["confidence"] >= cutoff]
    area_values = [row["clipped_area_m2"] for row in filtered if row["clipped_area_m2"] is not None]
    count = len(filtered)
    boundary_area = _float(summary, "boundary_area_km2")
    if minimum_conf > slider_min + 1e-9 and cutoff < minimum_conf:
        st.sidebar.warning(f"Source file contains predictions from confidence ≥ {minimum_conf:.2f}; lowering this control cannot add missing predictions.")

    with st.container(border=True):
        st.title("Lagos building footprint explorer")
        st.caption("Explore predicted building footprints, confidence scores, and export quality for a Lagos study area.")
    st.caption(f"Active dataset: {dataset_label} · Area: {summary.get('boundary_name', 'Unknown')} · Source: {summary.get('footprint_dataset', 'Unknown')}")

    overview, explore, technical, guide = st.tabs(["Overview", "Explore footprints", "Technical QA", "Guide & limits"], on_change="rerun")
    with overview:
        if overview.open:
            with st.container(horizontal=True):
                st.metric("Predictions shown", f"{count:,}", help="Predicted footprint features at or above the selected confidence score.", border=True)
                st.metric("Study area", f"{boundary_area:,.2f} km²" if boundary_area is not None else "Not reported", border=True)
                st.metric("Median confidence", f"{pd.Series([row['confidence'] for row in filtered if row['confidence'] is not None]).median():.3f}" if count else "—", border=True)
                st.metric("Median clipped area", f"{pd.Series(area_values).median():,.1f} m²" if area_values else "—", border=True)
            st.markdown("### Prediction locations")
            _render_map(filtered, boundary_bytes)
            st.info("Green points show locations of exported model predictions. Confidence is the source model's score, not measured local accuracy or a calibrated probability. The supplied export does not include reference labels, so this dashboard does not claim precision, recall, or completeness.", title="How to read this")

        if overview.open:
            left, right = st.columns([1.25, 1])
            with left:
                st.markdown("### Confidence profile")
                confidence_frame = pd.DataFrame({"Confidence": [row["confidence"] for row in filtered if row["confidence"] is not None]})
                if not confidence_frame.empty:
                    histogram = confidence_frame["Confidence"].clip(0, 1).pipe(lambda series: pd.cut(series, bins=20, include_lowest=True)).value_counts(sort=False).rename_axis("Confidence band").reset_index(name="Predicted footprints")
                    histogram["Band start"] = histogram["Confidence band"].map(lambda interval: interval.left)
                    histogram["Band end"] = histogram["Confidence band"].map(lambda interval: interval.right)
                    chart = alt.Chart(histogram).mark_bar(color="#168469").encode(
                        alt.X("Band start:Q", title="Model confidence", scale=alt.Scale(domain=[0, 1])),
                        alt.X2("Band end:Q"),
                        alt.Y("Predicted footprints:Q", title="Predicted footprints"),
                        tooltip=[alt.Tooltip("Band start:Q", format=".2f", title="From"), alt.Tooltip("Band end:Q", format=".2f", title="To"), "Predicted footprints:Q"],
                    ).properties(height=260)
                    st.altair_chart(chart, width="stretch", alt="Distribution of model confidence scores among the selected predictions")
            with right:
                st.markdown("### Export details")
                st.write({
                    "Selected Lagos area": summary.get("boundary_name", "Unknown"),
                    "Boundary source": summary.get("boundary_source", "Not stated"),
                    "Source dataset": summary.get("footprint_dataset", "Not stated"),
                    "Inference year": summary.get("source_inference_year", "Not stated"),
                    "Original cutoff": summary.get("minimum_confidence", "Not stated"),
                    "Exported at (UTC)": summary.get("export_started_utc", "Not stated"),
                    "Dataset license": summary.get("source_license", "Not stated"),
                })

            st.markdown("### Project-trained SpaceNet U-Net")
            try:
                model_metrics = json.loads(MODEL_METRICS.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                model_metrics = None
            if model_metrics:
                try:
                    test_metrics = json.loads(MODEL_TEST_METRICS.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    test_metrics = None
                with st.container(horizontal=True):
                    st.metric("Validation IoU", f"{model_metrics['best_validation_iou']:.3f}", border=True)
                    st.metric("Validation F1", f"{model_metrics['best_validation_f1']:.3f}", border=True)
                    st.metric("Test IoU", f"{test_metrics['test_pixel_iou']:.3f}" if test_metrics else "Not run", border=True)
                    st.metric("Test F1", f"{test_metrics['test_pixel_f1']:.3f}" if test_metrics else "Not run", border=True)
                st.caption(
                    f"Four-level U-Net trained on {model_metrics['training_source']} · "
                    f"{model_metrics['epochs']} epochs on {model_metrics['device']} · "
                    f"{model_metrics['train_source_images']} train scenes / {model_metrics['train_tiles']:,} tiles · "
                    f"{model_metrics['validation_source_images']} validation scenes / "
                    f"{model_metrics['validation_tiles']:,} tiles · "
                    + (f"{test_metrics['test_source_images']} separate test scenes / {test_metrics['test_tiles']:,} tiles."
                       if test_metrics else "Test scenes not evaluated yet.")
                )
                history = pd.DataFrame(model_metrics.get("history", []))
                if not history.empty:
                    loss_history = history.melt(
                        id_vars="epoch",
                        value_vars=["train_loss", "validation_loss"],
                        var_name="Split",
                        value_name="Dice + focal loss",
                    )
                    loss_history["Split"] = loss_history["Split"].map({
                        "train_loss": "Training",
                        "validation_loss": "Validation",
                    })
                    loss_chart = alt.Chart(loss_history).mark_line(point=True).encode(
                        x=alt.X("epoch:Q", title="Epoch", axis=alt.Axis(tickMinStep=1)),
                        y=alt.Y("Dice + focal loss:Q", title="Dice + focal loss"),
                        color=alt.Color("Split:N", title="Dataset split"),
                        tooltip=["epoch:Q", "Split:N", alt.Tooltip("Dice + focal loss:Q", format=".3f")],
                    ).properties(height=220)
                    st.altair_chart(loss_chart, width="stretch", alt="Training and validation loss by epoch")
                st.info(
                    "Validation and test scenes come from SpaceNet AOI 2 Las Vegas; the test scenes were not used for training or checkpoint selection. "
                    "These metrics measure performance within the Las Vegas dataset; they are not Lagos accuracy. "
                    "Lagos inference requires compatible high-resolution Lagos imagery.",
                    title="U-Net validation context",
                )
                if MODEL_TEST_PREVIEW.is_file():
                    st.image(
                        str(MODEL_TEST_PREVIEW),
                        alt="SpaceNet test scene 291 shown as RGB imagery, reference building labels, and project U-Net predictions",
                    )
                    st.caption("Qualitative example from one held-out Las Vegas test scene; it is not Lagos imagery.")
            else:
                st.info("No project-trained U-Net metrics are saved yet. The current map above is the separate Open Buildings V3 baseline.")

    with explore:
        if explore.open:
            st.markdown("### Explore and export a confidence-filtered subset")
            st.caption("Use the confidence control in the sidebar. Filters respond immediately to the features included in the active export.")
            st.caption("The attribute CSV includes source feature IDs, confidence, clipped area, geometry type, and approximate bounding-box centers for mapping.")
            display_rows = [{key: row[key] for key in ("id", "confidence", "clipped_area_m2", "geometry_type", "longitude", "latitude")} for row in filtered]
            if st.toggle("Show attribute preview", value=False, key="show-attributes"):
                st.dataframe(pd.DataFrame(display_rows[:5000]), width="stretch", height=360, hide_index=True, alt="Attributes for the first 5,000 filtered footprint predictions")
                if len(display_rows) > 5000:
                    st.caption(f"Preview limited to the first 5,000 of {len(display_rows):,} filtered features. Download the CSV for the full table.")
            geojson_out, csv_out = _make_downloads(filtered, dataset["geojson"])
            safe_name = "".join(ch.lower() if ch.isalnum() else "_" for ch in summary.get("boundary_name", "lagos")).strip("_") or "lagos"
            dl1, dl2 = st.columns(2)
            dl1.download_button("Download filtered GeoJSON", data=geojson_out, file_name=f"{safe_name}_footprints_conf{cutoff:.2f}.geojson", mime="application/geo+json", width="stretch")
            dl2.download_button("Download attribute CSV", data=csv_out, file_name=f"{safe_name}_footprints_conf{cutoff:.2f}.csv", mime="text/csv", width="stretch")
            if st.button("Save filtered outputs into results/interactive", icon=":material/save:"):
                saved = _save_interactive_outputs(ROOT / "results" / "interactive", safe_name, cutoff, geojson_out, csv_out, geojson_bytes, summary_bytes, len(filtered))
                st.success("Saved the filtered GeoJSON, attribute CSV, and reproducibility record.")
                st.code("\n".join(str(path.relative_to(ROOT)) for path in saved), language="text")

    with technical:
        if technical.open:
            st.markdown("### Reproducible export checks")
            st.caption("These checks assess file structure and metadata. They do not measure prediction accuracy.")
            checks = structural_checks(dataset)
            st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True, alt="Structural quality checks for the selected footprint export")
            if boundary_bytes:
                st.markdown("#### Optional exact boundary containment")
                st.caption("This checks every footprint geometry against the uploaded boundary and may take a little time. The result is cached for the current files.")
                if st.button("Verify all footprints against boundary", type="primary"):
                    try:
                        boundary_result = verify_boundary(geojson_bytes, boundary_bytes)
                        st.success(f"{boundary_result['contained']:,} of {boundary_result['total']:,} footprints are fully contained by the supplied boundary.")
                        if boundary_result["outside_or_invalid"]:
                            st.warning(f"{boundary_result['outside_or_invalid']:,} features are outside or invalid; {boundary_result['invalid_geometries']:,} have invalid or missing geometries.")
                            st.caption("First affected feature IDs: " + ", ".join(boundary_result["outside_ids"]))
                        else:
                            st.info("All supplied footprint geometries are valid and covered by the uploaded boundary.")
                    except Exception as exc:
                        st.error(f"Boundary check failed: {exc}")
            st.markdown("### Dataset profile")
            p1, p2, p3 = st.columns(3)
            p1.metric("GeoJSON features", f"{len(rows):,}")
            p2.metric("Observed confidence range", f"{min(dataset['confidence']):.3f}–{max(dataset['confidence']):.3f}" if dataset["confidence"] else "—")
            p3.metric("Feature-area sum", f"{sum(dataset['areas']) / 1_000_000:,.2f} km²" if dataset["areas"] else "—")
            st.caption("Feature-area sum is the sum of clipped feature areas. Overlapping predictions can be counted more than once; it is not a building coverage estimate.")
            st.markdown("### Reproducibility fingerprints")
            st.code(f"GeoJSON SHA-256  {hashlib.sha256(geojson_bytes).hexdigest()}\nSummary CSV SHA-256  {hashlib.sha256(summary_bytes).hexdigest()}", language="text")
            try:
                qa = json.loads(QA_SUMMARY.read_text(encoding="utf-8"))
                with st.expander("Supplied export's saved QA summary"):
                    st.json(qa)
            except (OSError, json.JSONDecodeError):
                pass

    with guide:
        if guide.open:
            st.markdown("### For a general audience")
            st.write("Each dot is a building footprint predicted by Google Research Open Buildings V3. The app lets you explore locations and confidence scores for the exported Lagos area. Higher confidence means the source model was more confident; it does not guarantee that the footprint is correct on the ground.")
            st.markdown("### For technical users")
            st.write("The source is an Earth Engine export of Open Buildings V3, filtered by a confidence threshold and clipped to a FAO GAUL 2025 level 2 Lagos boundary. Coordinates remain in WGS 84. The table and download controls expose a filtered subset of the features already in the GeoJSON.")
            st.markdown("### Known interpretation limits")
            st.write("The Ikeja map is the separate Google Research Open Buildings V3 baseline. Project-trained SpaceNet U-Net metrics, when present, are reported against held-out Las Vegas source images and do not establish Lagos accuracy. This project has not yet been validated against local Lagos reference labels or a field survey. Exact boundary containment remains unverified unless the matching boundary GeoJSON is supplied and the optional exact check is run in Technical QA.")
            st.markdown("### Run locally")
            st.code("python -m venv .venv\n.venv\\Scripts\\Activate.ps1\npip install -r requirements-app.txt\nstreamlit run app.py", language="powershell")
            st.caption("Downloads are saved by your browser to its configured Downloads folder. The app does not upload your files to a server.")


main()
