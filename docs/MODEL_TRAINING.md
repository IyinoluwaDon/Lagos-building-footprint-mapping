# SpaceNet U-Net Training and Lagos Transfer

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

1. Download and extract the official SpaceNet 2 AOI 2 Vegas building training archive.
2. Run `python -m lagos_buildings.prepare` with its `RGB-PanSharpen` and `geojson/buildings` folders.
3. Run `python -m lagos_buildings.train` to save the selected model and validation metrics.
4. Supply georeferenced Lagos RGB imagery and a Lagos boundary to `python -m lagos_buildings.predict`.

Training imagery, chips, model weights, metrics, and Lagos predictions are generated locally and are excluded from Git.
