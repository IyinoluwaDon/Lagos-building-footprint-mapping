# Ikeja export data dictionary

## Files

- `Ikeja_open_buildings_conf075.geojson` — 53,437 clipped building-footprint predictions.
- `Ikeja_open_buildings_conf075_summary.csv` — one-row export metadata from Earth Engine.
- `Ikeja_boundary_gaul2025.geojson` — not included in the supplied export. The updated notebook can export it for independent boundary containment checks.

## GeoJSON feature properties

| Property | Meaning | Unit / interpretation |
|---|---|---|
| `confidence` | Open Buildings model confidence for the predicted footprint | Unitless score from 0 to 1; this export uses a minimum of 0.75 |
| `clipped_area_m2` | Area after intersecting the source footprint with the selected LGA | Square metres; per-feature sum may include overlap and is not a coverage estimate |
| GeoJSON `id` | Earth Engine feature identifier at the top level of each feature | String identifier; expected unique in this export |

Coordinates use WGS 84 longitude, latitude (EPSG:4326). Feature geometry is Polygon or MultiPolygon. Geometries are clipped to the chosen AOI by the notebook.

## Summary CSV fields

The export summary records the boundary name and source, boundary area in square kilometres, Earth Engine export start time in UTC, filtered feature count, source dataset, confidence threshold, source inference year, and source license. The summary table may also include an empty `.geo` column and `system:index` as row-level export bookkeeping fields. The GeoJSON feature identifier is stored in the feature-level `id`, not in `properties`.

## Provenance and limits

Source footprints: Google Research Open Buildings V3, inference year 2023. Boundary layer: FAO GAUL 2025 level 2. The supplied GeoJSON and CSV are source exports; generated QA reports and figures are derived outputs. The model confidence score is not an accuracy probability calibrated for Ikeja. The feature count is not a building census. Exact containment against the exported boundary cannot be checked until the matching boundary GeoJSON is added beside these files.
