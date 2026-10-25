# Lagos Building Footprint Extraction with U-Net

This project adds a trainable building-segmentation model to the Lagos Open Buildings workflow. Its four-level U-Net training pipeline uses SpaceNet 2 AOI 2 Vegas RGB-PanSharpen imagery and rasterized building polygons; the inference pipeline applies a trained checkpoint to compatible high-resolution imagery clipped to a Lagos boundary. The repository currently contains the pipeline, not a trained checkpoint or Lagos U-Net predictions. The existing Google Research Open Buildings V3 export remains available as a separately sourced Lagos-area baseline.

## Model and training workflow

- **Architecture:** four-level U-Net encoder-decoder with skip connections, RGB input, and one building-probability output channel.
- **Training data:** SpaceNet 2 AOI 2 Las Vegas RGB-PanSharpen images and paired building GeoJSON polygons.
- **Label preparation:** polygon labels are rasterized against each image's own CRS and affine transform, then images and masks are tiled together.
- **Split:** source images, not individual chips, are assigned to train or validation so neighboring tiles from one source image cannot leak across the split.
- **Loss and optimizer:** soft Dice loss plus binary focal loss; Adam optimizer.
- **Model selection:** retain the checkpoint with the best image-held-out IoU; report IoU and F1 at the configured probability threshold.
- **Lagos inference:** slide the trained model over a georeferenced RGB GeoTIFF, average overlapping chip predictions, clip the raster and vectorized footprints to the supplied Lagos boundary, and write a probability GeoTIFF plus GeoJSON.

The training pipeline is in `src/lagos_buildings/`. Running it generates training metrics and a model checkpoint. The existing Streamlit app explores the supplied Open Buildings V3 prediction export; it is separate from U-Net training and inference.

## Prepare the SpaceNet training data

SpaceNet hosts the AOI 2 Vegas training archive as a public dataset. The official archive is large, so download and extract it on a machine with sufficient disk space. The archive contains RGB-PanSharpen GeoTIFFs and matching building GeoJSON labels. See the [SpaceNet 2 dataset page](https://spacenet.ai/spacenet-buildings-dataset-v2/) for the download and citation details.

Install the model dependencies from the repository root:

```powershell
python -m pip install -e ".[model]"
```

Prepare 256 × 256 image and mask chips. Replace the paths with the extracted archive's folders:

```powershell
python -m lagos_buildings.prepare `
  --images data/spacenet/SN2_buildings_train_AOI_2_Vegas/RGB-PanSharpen `
  --labels data/spacenet/SN2_buildings_train_AOI_2_Vegas/geojson/buildings `
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
  --epochs 30 `
  --batch-size 8
```

The run writes the selected checkpoint to `outputs/unet_spacenet2_vegas.pt` and epoch-level training/validation metrics to `outputs/unet_spacenet2_vegas.metrics.json`.

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

## Repository map

- `src/lagos_buildings/model.py` — U-Net architecture and Dice + focal loss.
- `src/lagos_buildings/prepare.py` — SpaceNet image/label pairing, rasterization, image-level split, and tiling.
- `src/lagos_buildings/train.py` — training loop, validation metrics, and checkpoint selection.
- `src/lagos_buildings/predict.py` — tiled Lagos inference, boundary clipping, and raster-to-polygon output.
- `notebooks/lagos_open_buildings_gee.ipynb` — existing Earth Engine export of Open Buildings V3 predictions.
- `results/lagos/` — supplied Ikeja prediction export and local QA artifacts.
- `app.py` — interactive viewer for the supplied Open Buildings export.
- `docs/MODEL_TRAINING.md` — model workflow details and data preparation notes.
- `docs/METHOD_AND_REPRODUCIBILITY.md` — export, model, and local audit reproduction.
