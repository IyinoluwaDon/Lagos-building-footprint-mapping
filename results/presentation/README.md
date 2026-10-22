# Lagos presentation deliverables

Run `notebooks/lagos_open_buildings_gee.ipynb` to export these files to `My Drive/Lagos_Open_Buildings/`:

- `<LGA>_open_buildings_conf075.geojson` — clipped footprint features;
- `<LGA>_open_buildings_conf075_summary.csv` — boundary area, confidence cutoff, footprint count, source year, and export time.

After both Earth Engine tasks finish, download the files from Drive. Keep source exports in `results/lagos/`; use the GeoJSON to create a map in QGIS and use the summary CSV for the presentation numbers. Follow [`SLIDE_OUTLINE.md`](SLIDE_OUTLINE.md) to structure the slides.

The export has not been run yet, so there are no measured Lagos results or final map in this folder. The feature count describes the filtered source dataset; it is not an independent accuracy measurement.
