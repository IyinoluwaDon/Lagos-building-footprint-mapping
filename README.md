# Lagos building footprints

This repository contains one workflow: export existing Google Research Open Buildings V3 footprints clipped to a single Lagos Local Government Area (LGA). The default is Ikeja. The workflow runs in Google Colab and uses Earth Engine; it does not download a large imagery archive or require this project to be copied to Drive.

## Run it

1. Open [`notebooks/lagos_open_buildings_gee.ipynb`](notebooks/lagos_open_buildings_gee.ipynb) in Google Colab. Upload that notebook only.
2. Run the cells from top to bottom. Sign in when Earth Engine prompts you and enter your Earth Engine enabled Google Cloud Project ID.
3. Choose a Lagos LGA from the printed list, or press Enter to use Ikeja.
4. Wait for both Earth Engine export tasks to report `COMPLETED`.

Earth Engine saves these files to `My Drive/Lagos_Open_Buildings/`:

- `<LGA>_open_buildings_conf075.geojson`: Open Buildings footprints clipped to the selected boundary;
- `<LGA>_open_buildings_conf075_summary.csv`: LGA name and area, confidence threshold, footprint count, dataset, source year, and export timestamp.

The notebook displays an interactive preview. Download the exports from Drive if you want a local copy under [`results/lagos/`](results/lagos/) or to build the map for a presentation. [`results/presentation/SLIDE_OUTLINE.md`](results/presentation/SLIDE_OUTLINE.md) describes a short presentation based on the actual export.

## Data and limits

The notebook filters the existing `GOOGLE/Research/open-buildings/v3/polygons` layer at confidence >= 0.75 and clips intersecting features to the selected FAO GAUL 2025 level 2 boundary. It exports model-derived building footprints; it does not independently detect or validate buildings. The feature count is a count of filtered source predictions, not an accuracy score, and the layer should not be described as a complete or surveyed building register.

Credit Google Research Open Buildings V3 and FAO GAUL 2025 under CC BY 4.0 when reusing the data. No Lagos export is included yet. Run the notebook with your Earth Engine account to generate the project results.
