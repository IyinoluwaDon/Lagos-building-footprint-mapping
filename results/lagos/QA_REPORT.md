# Ikeja Open Buildings export: data quality report

Analysis run (UTC): 2026-10-25T18:37:25.288828+00:00
Runtime: Python 3.12.14, Pillow 13.0.0, Shapely 2.2.0.
Boundary: Ikeja LGA; 46.016 km² per the supplied summary CSV.
Source: Google Research Open Buildings V3 (inference year 2023); confidence cutoff 0.75.

## Results

- Exported features: **53,437** (CSV reports 53,437).
- Prediction density: 1,161.3 features per km² of reported boundary area; this is not population density or a completeness estimate.
- Geometry types: MultiPolygon: 3, Polygon: 53,434.
- Confidence: mean 0.8536; median 0.8575; range 0.7500–0.9747.
- Confidence distribution: 0.75–0.80: 12,628, 0.80–0.85: 12,142, 0.85–0.90: 13,945, 0.90–0.95: 14,057, 0.95–1.00: 665.
- Clipped feature area: median 124.1 m²; 90th percentile 399.7 m²; maximum 19,394.0 m².
- Sum of per-feature clipped areas: 11.854 km². This is a non-dissolved sum and is not an area-coverage estimate.
- Exported coordinate extent: 3.316302–3.383110°E, 6.551081–6.657096°N.

## Checks

- PASS — geojson feature count matches summary csv.
- PASS — all confidence values meet minimum.
- PASS — confidence scores within unit interval.
- PASS — all clipped areas are positive.
- PASS — unique feature ids.
- PASS — polygon rings closed and coordinates wgs84.
- PASS — feature geometries present.
- PASS — polygon topology valid.
- **NOT VERIFIED** — NOT RUN — matching GAUL 2025 boundary GeoJSON was not supplied.

Not possible from the supplied files; rerun the updated notebook and add its matching boundary GeoJSON.

## Reproduction

From the repository root, install the analysis dependencies and rerun:

```powershell
python -m pip install -r results/lagos/requirements-analysis.txt
python results/lagos/analyze_export.py
```

For a different Lagos LGA, pass its matching inputs explicitly:

```powershell
python results/lagos/analyze_export.py --geojson results/lagos/<LGA>_open_buildings_conf075.geojson --summary-csv results/lagos/<LGA>_open_buildings_conf075_summary.csv --boundary-geojson results/lagos/<LGA>_boundary_gaul2025.geojson
```

SHA-256 GeoJSON: `8832c6035c7ce73cbd7cea8733d52138e85199a6a46a96bbfd96e33070d1f8e1`  
SHA-256 summary CSV: `4e7fca6c3e180a0424737e3b22cb0bac68cf422d477d5c1e8b41a89c8f359a46`
