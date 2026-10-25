# Method and reproducibility

This document covers the SpaceNet U-Net training/test/inference pipeline and the Lagos Open Buildings V3 export/QA workflow. See `MODEL_TRAINING.md` for model design, loss, data subset, split, and results. The compact model was trained and tested locally; Lagos U-Net inference has not been run because a compatible high-resolution Lagos image is not in the project files.

## U-Net training

The training source is SpaceNet 2 AOI 2 Vegas RGB-PanSharpen imagery paired by image ID with building GeoJSON. `src/lagos_buildings/prepare.py` reprojects each polygon collection to its image CRS, rasterizes masks against the image transform, splits by source image, and emits aligned chips. Training imagery supplies per-band 2nd and 98th percentile normalization values, which are recorded in the manifest and checkpoint for Lagos inference.

`src/lagos_buildings/model.py` defines a four-level U-Net with RGB input and a one-channel building-logit head. `src/lagos_buildings/train.py` optimizes Dice plus binary focal loss with Adam. The seeded 48-scene subset produced 377 chips, trained for five CPU epochs (base width 8), and selected a checkpoint using image-held-out validation IoU. Validation IoU/F1 were 0.516/0.680 at threshold 0.5. The saved checkpoint and epoch history are `outputs/unet_spacenet2_vegas.pt` and `outputs/unet_spacenet2_vegas.metrics.json`.

The final test sample is separate: 12 scene pairs were downloaded after excluding every training/validation ID, and 10 unseen source scenes (90 chips) were evaluated by `src/lagos_buildings/evaluate.py`. The script checks disjoint scene IDs before evaluation. Test pixel IoU/F1 were 0.597/0.748 at threshold 0.5; results are saved to `outputs/unet_spacenet2_vegas.test_metrics.json`. These are in-domain SpaceNet Vegas metrics, not Lagos transfer metrics.

## Lagos U-Net inference

`src/lagos_buildings/predict.py` reads one georeferenced RGB image tile and a Lagos boundary GeoJSON. Overlapping model windows are averaged into a probability raster. The thresholded mask is polygonized, intersected with the boundary, and saved as WGS 84 GeoJSON. The raster keeps the source image CRS and transform. The existing Open Buildings V3 export provides a Lagos footprint baseline; it does not provide the source image consumed by the U-Net.

## Cloud export

The Colab notebook authenticates with the user's Earth Engine-enabled Google Cloud project. It reads FAO GAUL 2025 level 2 administrative boundaries, filters to the Lagos state boundaries, prompts for an LGA and a confidence cutoff, then filters `GOOGLE/Research/open-buildings/v3/polygons` server-side. It previews rasterized map tiles without downloading the full source collection into Colab. Earth Engine intersects each retained polygon with the chosen area and exports the clipped features, exact boundary, and a metadata CSV to `My Drive/Lagos_Open_Buildings/`.

The final notebook cell exports only the lightweight boundary and summary. It can be rerun by itself after a successful footprint export, avoiding a duplicate footprint export. In a fresh runtime, run authentication and boundary selection before that final cell; the notebook calculates the filtered count on Earth Engine.

## Local audit

The audit script reads the GeoJSON and its one-row summary, then checks:

- GeoJSON type and feature count against the CSV;
- presence, range, and minimum of confidence scores;
- positive finite clipped areas and nonempty unique feature IDs;
- Polygon/MultiPolygon rings, finite WGS 84 coordinates, and Shapely topology;
- coverage by the matching exported boundary when supplied.

It records input byte counts and SHA-256 hashes, runtime library versions, summary metrics, and check results. It writes JSON for downstream use, Markdown for review, plain-text logs, and map/distribution figures.

## Run from the repository root

```powershell
python -m pip install -r results/lagos/requirements-analysis.txt
python results/lagos/analyze_export.py
python -m unittest discover -s tests -v
```

For exports with other names, supply all matching input paths. Example:

```powershell
python results/lagos/analyze_export.py `
  --geojson results/lagos/<LGA>_open_buildings_conf080.geojson `
  --summary-csv results/lagos/<LGA>_open_buildings_conf080_summary.csv `
  --boundary-geojson results/lagos/<LGA>_boundary_gaul2025.geojson
```

You can also set `--presentation-dir`, `--report`, `--summary-json`, and `--log` to control derived output paths. The summary CSV is the source of the reported cutoff and boundary area; the script does not guess or override those values.

## Determinism and interpretation

Source hashes are stable for unchanged files; run timestamps and library versions change across runs. Figures and metrics are derived from the input exports. Model confidence is not a substitute for local accuracy assessment. Per-feature area sums may count overlaps more than once.
