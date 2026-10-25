# Technical notes: Lagos building footprint mapping

This is the technical companion to the [README](../README.md) and [model-training record](MODEL_TRAINING.md). It explains data formats, model operations, evaluation and the distinction between the Lagos baseline and the trained model.

## Two separate footprint products

The project currently contains two sources of footprints:

- **Open Buildings V3 Ikeja export:** precomputed Google Research detections exported from Earth Engine, filtered at confidence 0.75 and clipped to an administrative boundary. The local file has 53,437 features. It is the current Lagos-area map the Streamlit app can browse.
- **SpaceNet-trained U-Net:** the model created in this repository from SpaceNet 2 AOI 2 Las Vegas imagery and matching building polygons. The checkpoint has been trained, validated, tested, and run through inference on a held-out Las Vegas image. No U-Net result is yet claimed for Lagos because its required compatible high-resolution Lagos input image is not present.

These products must not be merged in reporting: Open Buildings detections are not U-Net predictions and SpaceNet metrics are not Lagos accuracy.

## Input data and labels

SpaceNet image objects are RGB-PanSharpen GeoTIFFs; labels are GeoJSON building polygons. `scripts/download_spacenet_subset.py` lists public S3 objects and downloads matched image/label pairs only, with resumable partials and a saved selection manifest. The compact run fetched 48 pairs for training/validation and 12 additional pairs for an independent scene sample rather than downloading the full archive.

`src/lagos_buildings/prepare.py` matches imagery and labels by scene ID, checks each source CRS, reprojects polygon vectors to the paired raster CRS, then rasterizes polygon interiors using the raster affine transform. `all_touched=False` labels pixels whose centers fall inside a polygon, avoiding a systematic outward dilation of small footprints. The mask uses 1 for building and 0 for background.

Images and masks are tiled together into 256×256 chips. Source images, not chips, are split into training and validation before tiling, preventing neighbouring chips from the same satellite image from crossing that split. The recorded 48-scene run uses 38 train and 10 validation scenes. Training tiles retain every positive chip and a seeded fraction of empty chips; validation preserves all chips. The preprocessing normalization is a per-band median across training-scene 2nd and 98th percentiles, scaled to the model input range and stored in the manifest/checkpoint.

The independent test sample excludes the training and validation scene IDs before download. Ten of the 12 downloaded scenes (90 chips) were evaluated; the other two were reserved and not used for fitting or scoring. `src/lagos_buildings/evaluate.py` checks the scene-ID disjointness against checkpoint metadata before computing test metrics.

## U-Net terminology and computation

`src/lagos_buildings/model.py` implements a four-level **U-Net**: each encoder block uses paired 3×3 convolutions, batch normalization and ReLU; max-pooling halves spatial dimensions while feature channels increase. The decoder upsamples with transposed convolutions, concatenates the matching encoder **skip connection**, and applies convolution blocks. A 1×1 output convolution produces one building **logit** per pixel. The training loss consumes logits; a sigmoid converts them to probabilities at evaluation/inference.

The saved run uses RGB input, base width 8, Adam with learning rate 1e-4, batch size 8, five epochs, and fixed seed 42. The objective is soft Dice loss plus binary focal loss. Dice loss rewards overlap under class imbalance; focal loss increases the contribution of hard pixel examples. The best checkpoint is selected by validation pixel IoU.

For binary masks, pixel IoU is TP/(TP+FP+FN); F1 is 2TP/(2TP+FP+FN). They are calculated after thresholding building probability at 0.5 and aggregating valid pixels across held-out tiles. Saved validation IoU/F1 are 0.516/0.680; independent SpaceNet test IoU/F1 are 0.597/0.748. This is a compact subset result, not a full SpaceNet benchmark.

## Lagos tiled inference

`src/lagos_buildings/predict.py` expects a georeferenced RGB GeoTIFF with a projected CRS, valid raster mask, and pixel sizes compatible with SpaceNet's approximately 0.3 m imagery, plus a boundary GeoJSON. It rejects missing CRS, nonprojected imagery, incompatible resolution, and nonintersecting boundaries.

Inference uses overlapping 256-pixel windows (default stride 128). Each window is normalized with the training checkpoint's stored band ranges. Batched sigmoid probabilities are accumulated and averaged by a per-pixel weight count, which reduces seams where windows overlap. Pixels outside the intersection of the boundary mask and valid imagery are written as raster NoData. The raster preserves source CRS/transform. Thresholded pixels are polygonized, intersected with the boundary geometry, and exported as WGS 84 GeoJSON.

The saved scene 291 preview and scratch raster/vector outputs document this inference path on held-out SpaceNet imagery. They are not a Lagos deployment output.

## Open Buildings export and QA terms

The Colab Earth Engine notebook filters the `GOOGLE/Research/open-buildings/v3/polygons` collection server-side by an administrative geometry and confidence threshold, then exports clipped polygons, boundary and summary metadata. **Confidence** is the source model's per-feature score and is not independently calibrated local accuracy. Clipping is geometric intersection with the selected boundary; it can split a source polygon and alter its geometry.

The local audit checks feature count against export metadata, confidence ranges, unique IDs, nonempty finite geometries, WGS 84 coordinates, Shapely topology, and boundary containment when the matching boundary export is supplied. A bounding-box or unrelated administrative geometry is not equivalent to checking the exact export boundary.

## App, artifacts and tests

The Streamlit app displays the existing Ikeja Open Buildings export, summary maps/figures, and the SpaceNet U-Net's separately labelled training/test metrics and qualitative held-out tile. It loads tracked lightweight outputs; it does not train, fetch satellite imagery or produce new Lagos U-Net predictions on page load.

`tests/test_unet_pipeline.py` covers architecture output shape, loss backpropagation and edge-tile window coverage. `tests/test_app_smoke.py` checks that the dashboard renders the baseline and model metrics and verifies that sampled map coordinates account for the exported features. The workflow installs CPU PyTorch plus app/model dependencies and runs pytest. Compile checks and the live Streamlit health endpoint complement the automated tests.

Useful terms: **GeoTIFF** is a raster with geospatial coordinate metadata; **GeoJSON** is a vector geometry interchange format; **CRS** is the coordinate reference system; **affine transform** maps raster indices to ground coordinates; **rasterization** converts vector geometry into a grid mask; **polygonization** converts contiguous classified pixels back to vector geometry; **IoU** is intersection over union; **held-out scene** is a source image excluded from model fitting and checkpoint selection.
