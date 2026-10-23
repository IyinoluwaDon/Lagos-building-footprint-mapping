# Lagos Building Footprint Mapping and Spatial QA

A small geospatial workflow and Streamlit dashboard for inspecting a supplied building-footprint export, checking geometry/confidence fields and summarizing mapped buildings by area.

## What is included

- Offline geometry and confidence checks
- Optional interactive dashboard
- Reusable analysis script for GeoJSON exports and a supplied boundary

## Run locally

```sh
python -m pip install -r requirements-app.txt
streamlit run app.py
```

## Verify

python -m pip install -r results/lagos/requirements-analysis.txt
python -m unittest discover -s tests -v

## Repository map

`app.py` contains the dashboard. `docs/` describes the project. `results/lagos/` contains saved export/analysis assets where available; notebooks and tests provide supporting analysis and QA.

## Evidence and limitations

Seven offline geometry/confidence tests pass. The supplied export can be inspected, but the authoritative study-boundary file is missing.

A footprint export is not a complete or authoritative building inventory. Without the exact boundary, containment within an administrative area is unverified. Confirm source date, attribution and license before reuse; inspect positional accuracy before policy or planning use.

## License

No repository license file is included. Unless the project owner adds a license, do not assume the code, data or model artifacts may be redistributed or reused. Verify third-party data and model terms separately.
