# Lagos Building Footprint Mapping and Spatial QA

A cloud-first geospatial workflow that exports and audits published building-footprint predictions for Lagos, then provides an interactive way to explore them. The project reuses the Google Research Open Buildings V3 model output; it does not train a new building detector.

## Data workflow

`notebooks/lagos_open_buildings_gee.ipynb` uses Google Earth Engine to select an administrative area from FAO GAUL 2025 level-2 boundaries, filter `GOOGLE/Research/open-buildings/v3/polygons` by confidence, clip predictions to the chosen area, and export the footprints, boundary, and source metadata. The supplied Ikeja export contains **53,437 predicted footprints at confidence >= 0.75** over a reported **46.0156 km2** area.

The local analysis checks GeoJSON structure, identifiers, coordinate ranges, geometry validity, areas, confidence values, and export metadata. The Streamlit dashboard filters, maps, profiles, and downloads subsets of the supplied prediction export. Results and data definitions are in `results/lagos/`; the workflow and QA details are in `docs/`.

## Run

```sh
python -m pip install -r requirements-app.txt
streamlit run app.py
```

For a fresh Earth Engine export, use the Colab notebook with an authenticated Google Cloud project. The app operates on the supplied export and does not issue a new Earth Engine query.
