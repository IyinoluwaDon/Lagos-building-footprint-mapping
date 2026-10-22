# Method and reproducibility

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
