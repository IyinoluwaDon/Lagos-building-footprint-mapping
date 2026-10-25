# Lagos Building Footprint Extraction with U-Net

This project trains its own four-level U-Net using real SpaceNet 2 AOI 2 Vegas RGB-PanSharpen scenes and paired building polygons. A compact model run has been trained and evaluated on 10 separate SpaceNet test scenes. Its test pixel IoU is **0.597** and F1 is **0.748** at threshold 0.5. Those are Las Vegas results; producing U-Net predictions for Lagos still requires compatible high-resolution Lagos RGB imagery. The existing Google Research Open Buildings V3 Ikeja export remains a separate Lagos baseline.

## Model and training workflow

- **Architecture:** four-level U-Net encoder-decoder with skip connections, RGB input, and one building-probability output channel.
- **Training data:** SpaceNet 2 AOI 2 Las Vegas RGB-PanSharpen images and paired building GeoJSON polygons.
- **Label preparation:** polygon labels are rasterized against each image's own CRS and affine transform, then images and masks are tiled together.
- **Split:** source images, not individual chips, are assigned to train, validation, and a disjoint final test set.
- **Loss and optimizer:** soft Dice loss plus binary focal loss; Adam optimizer.
- **Model selection:** retain the checkpoint with the best image-held-out IoU; report IoU and F1 at the configured probability threshold.
- **Lagos inference:** slide the trained model over a georeferenced RGB GeoTIFF, average overlapping chip predictions, clip the raster and vectorized footprints to the supplied Lagos boundary, and write a probability GeoTIFF plus GeoJSON.

The pipeline is in `src/lagos_buildings/`. The saved checkpoint and separate validation/test metrics are shown in the Streamlit app alongside the Open Buildings V3 baseline.

## Prepare the SpaceNet training data

SpaceNet's public AWS bucket stores individual RGB scenes and label GeoJSON files. The project downloader selects only matched scenes instead of fetching the 23 GB training archive. The recorded run used 48 training/validation pairs (117.27 MiB) and 12 additional pairs for a disjoint test sample (29.33 MiB). See the [SpaceNet 2 dataset page](https://spacenet.ai/spacenet-buildings-dataset-v2/) for dataset and citation details.

Install the model dependencies from the repository root. On CPU-only machines, install the CPU PyTorch build first:

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e ".[model]"
```

Fetch the small, seeded training and test subsets:

```powershell
python scripts/download_spacenet_subset.py --output data/spacenet --count 48 --seed 42
python scripts/download_spacenet_subset.py --output data/spacenet_test --count 12 --seed 43 --exclude-manifest data/spacenet/download_manifest.json
```

Prepare 256 × 256 image and mask chips:

```powershell
python -m lagos_buildings.prepare `
  --images data/spacenet/RGB-PanSharpen `
  --labels data/spacenet/geojson/buildings `
  --output data/spacenet_tiles `
  --tile-size 256 `
  --stride 256
```

The default preparation keeps all building-positive training chips and a seeded sample of empty training chips. Validation chips are retained for the full image-held-out validation split.

Train the model:

```powershell
python -m lagos_buildings.train `
  --tiles data/spacenet_tiles `
  --output outputs/unet_spacenet2_vegas.pt `
  --epochs 5 `
  --batch-size 8 `
  --base-channels 8
```

The saved compact run used 48 real scenes, 377 aligned chips, five epochs, batch size 8, and base width 8 on CPU. The source-image-level split used 38 scenes for training and 10 for validation. The held-out checkpoint-selection IoU/F1 were 0.516/0.680. A separate, never-trained-on test set used 10 disjoint scenes and 90 chips; test IoU/F1 were 0.597/0.748. This is an initial subset result rather than a full SpaceNet benchmark. The checkpoint and training history are `outputs/unet_spacenet2_vegas.pt` and `outputs/unet_spacenet2_vegas.metrics.json`.

Prepare and evaluate the separate test scenes:

```powershell
python -m lagos_buildings.prepare `
  --images data/spacenet_test/RGB-PanSharpen `
  --labels data/spacenet_test/geojson/buildings `
  --output data/spacenet_test_tiles `
  --tile-size 256 `
  --stride 256 `
  --validation-fraction 0.83 `
  --negative-keep-fraction 1.0

python -m lagos_buildings.evaluate `
  --tiles data/spacenet_test_tiles `
  --checkpoint outputs/unet_spacenet2_vegas.pt
```

## Apply the model to Lagos imagery

Supply a georeferenced RGB GeoTIFF at high resolution compatible with the SpaceNet training imagery and a GeoJSON boundary for the Lagos area being mapped. The supplied Open Buildings V3 GeoJSON contains predictions and does not contain the satellite image needed by the U-Net.

```powershell
python -m lagos_buildings.predict `
  --checkpoint outputs/unet_spacenet2_vegas.pt `
  --image data/lagos_imagery/lagos_tile.tif `
  --boundary data/lagos_imagery/lagos_boundary.geojson `
  --output-raster outputs/lagos_tile_building_probability.tif `
  --output-geojson outputs/lagos_tile_buildings.geojson
```

The probability raster preserves the image CRS and transform. The vector output is GeoJSON in WGS 84 and is clipped to the supplied boundary. Run the command once per image tile to process a larger Lagos area.

## Existing Lagos Open Buildings workflow

The Colab notebook `notebooks/lagos_open_buildings_gee.ipynb` selects a Lagos LGA, filters Google Research Open Buildings V3 predictions by confidence, and exports clipped footprints, a boundary, and source metadata. The supplied Ikeja export contains 53,437 predictions at a 0.75 confidence cutoff. It is a pre-existing model output, separate from the SpaceNet-trained U-Net.

Install the dashboard dependencies and launch the existing export viewer:

```powershell
python -m pip install -r requirements-app.txt
streamlit run app.py
```

The overview shows the supplied Ikeja Open Buildings baseline and reports the SpaceNet U-Net training, validation, and independent test results separately. It also includes an image/label/prediction comparison for held-out SpaceNet scene 291.

Run the complete project and app test suite:

```powershell
python -m pytest -q
```

## Repository map

- `src/lagos_buildings/model.py` — U-Net architecture and Dice + focal loss.
- `src/lagos_buildings/prepare.py` — SpaceNet image/label pairing, rasterization, image-level split, and tiling.
- `src/lagos_buildings/train.py` — training loop, validation metrics, and checkpoint selection.
- `src/lagos_buildings/evaluate.py` — held-out test evaluation that checks scene IDs are disjoint from training and validation.
- `scripts/download_spacenet_subset.py` — downloads only a seeded sample of matched public SpaceNet image/label objects.
- `outputs/model_test_scene291_preview.png` — held-out SpaceNet image, reference labels, and U-Net predictions.
- `src/lagos_buildings/predict.py` — tiled Lagos inference, boundary clipping, and raster-to-polygon output.
- `notebooks/lagos_open_buildings_gee.ipynb` — existing Earth Engine export of Open Buildings V3 predictions.
- `results/lagos/` — supplied Ikeja prediction export and local QA artifacts.
- `app.py` — Open Buildings explorer with separate U-Net validation and test results.
- `docs/MODEL_TRAINING.md` — model workflow details and data preparation notes.
- `docs/METHOD_AND_REPRODUCIBILITY.md` — export, model, and local audit reproduction.
