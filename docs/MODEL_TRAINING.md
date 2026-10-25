# SpaceNet U-Net Training and Lagos Transfer

## Completed compact model run

The project now includes a U-Net trained from real SpaceNet 2 AOI 2 Vegas RGB-PanSharpen scenes and their paired building GeoJSON labels. The seeded training/validation sample uses 48 source scenes (117.27 MiB downloaded), converted to 377 aligned 256 × 256 chips. A source-image split assigns 38 scenes to training and 10 to validation. The four-level RGB U-Net used base width 8, soft Dice plus binary focal loss, Adam at 1e-4, batch size 8, and five CPU epochs. The best checkpoint's validation pixel IoU/F1 at threshold 0.5 are 0.516/0.680.

A separate sample of 12 additional scene pairs (29.33 MiB) was downloaded with all training and validation IDs excluded. Ten of these unseen scenes (90 chips) form the final test split; the other two are not used in model training or scoring. The untouched test pixel IoU is 0.597 and F1 is 0.748 at the same threshold. The checkpoint, training history, and test metrics are saved under `outputs/`. This small, reproducible subset run demonstrates that the model was trained and tested; it is not a full-dataset benchmark or a Lagos accuracy result.

The training subset manifest, model/validation metrics, test metrics, and code record scene IDs and checks the final test IDs against training and checkpoint-selection IDs. Downloaded imagery and prepared chips remain local and ignored by Git.

## Training data and masks

The model uses the RGB-PanSharpen images and building GeoJSON polygons from SpaceNet 2 AOI 2 Las Vegas. Each polygon collection is reprojected to its paired image CRS and rasterized using that image's affine transform. The resulting binary mask uses 1 for building pixels and 0 for background.

The preparation script pairs image and label files by their `img` identifier. It splits whole source images into training and validation groups before creating chips. This keeps all chips from a source image on one side of the split. Chips are 256 × 256 pixels by default; the final row and column positions cover the image edges. All validation chips are kept, while the default training set keeps every building-positive chip and a reproducible 25% sample of background-only chips.

## Network and optimization

The model is a four-level U-Net. Each encoder and decoder stage has two 3 × 3 convolution, batch-normalization, and ReLU layers. Max pooling reduces encoder resolution; transposed convolutions upsample decoder features; skip connections join matching encoder and decoder maps. A 1 × 1 convolution returns one building logit per pixel.

Training minimizes soft Dice loss plus binary focal loss. Adam uses a default learning rate of 1e-4. Preparation derives per-band lower and upper bounds from the 2nd and 98th percentiles of the training source images, using the median bounds across source images. It scales chips to 8-bit values, and the checkpoint stores the original bounds. Inference reuses those bounds on target imagery before scaling inputs to `[0, 1]`. The best checkpoint is selected by IoU on image-held-out validation tiles; the configured 0.5 threshold is used to report IoU and F1.

## Lagos transfer inference

Inference reads one georeferenced RGB GeoTIFF tile at a time. Overlapping windows are passed through the trained model and averaged into a probability surface. The supplied Lagos GeoJSON is reprojected to the image CRS and rasterized to mask the probability output. Thresholded building pixels are polygonized, intersected with the vector boundary, and written to WGS 84 GeoJSON. The probability surface is also saved as a GeoTIFF using the input tile's CRS and transform.

The SpaceNet training imagery is WorldView-3 pansharpened RGB at approximately 0.3 m resolution. Lagos inference imagery should use a comparable high-resolution RGB source and radiometric scaling. The project's existing Open Buildings V3 export supplies footprint predictions, not the image chips consumed by this network.

## Reproduction

1. Run `python scripts/download_spacenet_subset.py --output data/spacenet --count 48 --seed 42` to fetch a compact matched sample from the public bucket.
2. Run `python scripts/download_spacenet_subset.py --output data/spacenet_test --count 12 --seed 43 --exclude-manifest data/spacenet/download_manifest.json` for a disjoint test sample.
3. Run `python -m lagos_buildings.prepare` with the downloaded `RGB-PanSharpen` and `geojson/buildings` folders.
4. Train using the training command in the README, prepare the test scenes separately, and run `python -m lagos_buildings.evaluate`.
5. Supply compatible georeferenced Lagos RGB imagery and a Lagos boundary to `python -m lagos_buildings.predict`.

Downloaded imagery, prepared chips, and generated Lagos inference rasters/footprints are local and ignored. The compact trained checkpoint and validation/test metrics are tracked so the app can show the actual run.
