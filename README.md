# Project 2: Lagos building footprint mapping

A cloud-first geospatial workflow to export, audit, explain, and present existing building-footprint predictions for a selected Lagos LGA. Google Earth Engine processes the Open Buildings layer on the server; the notebook previews map tiles and exports clipped vectors without downloading a large imagery archive.

This project reuses Google Research Open Buildings V3. It does **not** train a model or independently measure local building detection accuracy.

## Project question

What footprints does Open Buildings V3 predict inside a selected Lagos LGA at a chosen confidence cutoff, and which properties of the export can be checked reproducibly?

## Quick start

1. Open [`notebooks/lagos_open_buildings_gee.ipynb`](notebooks/lagos_open_buildings_gee.ipynb) in Colab. Upload the notebook; you do not need to upload this whole repository to Drive.
2. Run the setup and boundary-selection cells. Authenticate to Earth Engine with your Google account and enter your Earth Engine enabled Google Cloud Project ID.
3. Select a Lagos LGA and a confidence cutoff (default 0.75; 0.00–1.00 in 0.01 increments).
4. Run the footprint export cell, then the final boundary and summary export cell. Wait for each Earth Engine task to complete.

The exports appear in `My Drive/Lagos_Open_Buildings/`:

- `<LGA>_open_buildings_conf<TAG>.geojson` — clipped footprint predictions;
- `<LGA>_boundary_gaul2025.geojson` — the exact study boundary;
- `<LGA>_open_buildings_conf<TAG>_summary.csv` — area, cutoff, count, source, license, and export time.

The final notebook cell can be rerun by itself to refresh the small boundary and CSV without repeating the footprint export. On a fresh runtime, authenticate and select the boundary first; the notebook counts qualifying predictions on Earth Engine without downloading their geometries.

## Supplied Ikeja export

The current local dataset contains 53,437 predictions at confidence ≥ 0.75 for the 46.016 km² boundary reported in the summary CSV. Median confidence is 0.8575. The QA script confirms the count, threshold, identifiers, coordinates, ring closure, positive clipped areas, and polygon topology. The matching boundary GeoJSON is not in the supplied files, so independent boundary containment is not yet verified.

Use the data dictionary for field definitions and the project overview for the research question, workflow, and interpretation boundaries:

- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)
- [`docs/METHOD_AND_REPRODUCIBILITY.md`](docs/METHOD_AND_REPRODUCIBILITY.md)
- [`results/lagos/DATA_DICTIONARY.md`](results/lagos/DATA_DICTIONARY.md)
- [`docs/ASSESSMENT.md`](docs/ASSESSMENT.md)

## Local analysis

From the repository root:

```powershell
python -m pip install -r results/lagos/requirements-analysis.txt
python results/lagos/analyze_export.py
python -m unittest discover -s tests -v
```

To analyze a different LGA export, pass the matching files:

```powershell
python results/lagos/analyze_export.py `
  --geojson results/lagos/<LGA>_open_buildings_conf080.geojson `
  --summary-csv results/lagos/<LGA>_open_buildings_conf080_summary.csv `
  --boundary-geojson results/lagos/<LGA>_boundary_gaul2025.geojson
```

The script reads the threshold and boundary area from the summary CSV. It validates geometry and metadata, checks the exact boundary when supplied, records hashes and runtime versions, and produces JSON, Markdown, logs, and presentation figures. Use command options for custom output locations. Run `python results/lagos/analyze_export.py --help` for details.

## Results and repository map

- `notebooks/` — Earth Engine/Colab export workflow.
- `docs/` — project question, technical workflow, and candid quality assessment.
- `results/lagos/` — source exports, data dictionary, reproducible QA and machine-readable results.
- `results/presentation/` — complete project presentation, generated figures, and slide guidance.
- `tests/` — fast unit checks for confidence binning and geometry rings.

The [project presentation](results/presentation/Project_2_Lagos_Building_Footprint_Mapping.pptx) covers project purpose, design, data provenance, analysis, quality controls, interpretation, limitations, and next steps; it is not limited to the final map and counts.

## Data credits and limits

Credit [Google Research Open Buildings V3](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3_polygons) and [FAO GAUL 2025 level 2](https://developers.google.com/earth-engine/datasets/catalog/FAO_GAUL_2025_level2) under CC BY 4.0 when reusing the data. The model confidence score is not a locally calibrated accuracy probability. The output is not a complete building register. The sum of per-feature areas is not a coverage estimate because overlaps are not removed. Accuracy claims require an independent reference dataset and a documented sampling design.
