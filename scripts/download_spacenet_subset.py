"""Download a small, reproducible set of SpaceNet 2 Vegas image/label pairs.

The public S3 bucket stores scene files independently. This script lists the
image and label keys, samples matched scene IDs, and downloads only those pairs;
it never fetches the 23 GB training archive.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


BUCKET_URL = "https://spacenet-dataset.s3.amazonaws.com/"
IMAGE_PREFIX = "spacenet/SN2_buildings/train/AOI_2_Vegas/PS-RGB/"
LABEL_PREFIX = "spacenet/SN2_buildings/train/AOI_2_Vegas/geojson_buildings/"
NAMESPACE = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
IMAGE_ID = re.compile(r"_img(\d+)\.tif$", re.IGNORECASE)
LABEL_ID = re.compile(r"_img(\d+)\.geojson$", re.IGNORECASE)


def _list_objects(prefix: str) -> dict[str, tuple[str, int]]:
    token = None
    objects: dict[str, tuple[str, int]] = {}
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        request = urllib.request.Request(
            BUCKET_URL + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": "lagos-building-footprint-project/1.0"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            root = ET.fromstring(response.read())
        for item in root.findall("s3:Contents", NAMESPACE):
            key = item.findtext("s3:Key", namespaces=NAMESPACE)
            size = item.findtext("s3:Size", namespaces=NAMESPACE)
            if key and size:
                filename = key.rsplit("/", 1)[-1]
                match = IMAGE_ID.search(filename) if prefix == IMAGE_PREFIX else LABEL_ID.search(filename)
                if match:
                    objects[match.group(1)] = (key, int(size))
        token = root.findtext("s3:NextContinuationToken", namespaces=NAMESPACE)
        if not token:
            return objects


def _download(key: str, expected_size: int, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size == expected_size:
        return False
    url = BUCKET_URL + urllib.parse.quote(key, safe="/")
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(5):
        try:
            offset = temporary.stat().st_size if temporary.exists() else 0
            headers = {"User-Agent": "lagos-building-footprint-project/1.0"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=300) as response:
                append = offset > 0 and response.status == 206
                mode = "ab" if append else "wb"
                with temporary.open(mode) as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            actual_size = temporary.stat().st_size
            if actual_size != expected_size:
                raise IOError(f"Size mismatch for {key}: expected {expected_size}, got {actual_size}")
            temporary.replace(destination)
            return True
        except Exception:
            if attempt == 4:
                raise
            time.sleep(min(3 * (attempt + 1), 15))
    raise RuntimeError(f"Download failed after retries: {key}")


def download_subset(
    output: Path,
    *,
    count: int = 48,
    seed: int = 42,
    exclude_ids: set[str] | None = None,
) -> dict:
    images = _list_objects(IMAGE_PREFIX)
    labels = _list_objects(LABEL_PREFIX)
    excluded = exclude_ids or set()
    paired_ids = sorted((images.keys() & labels.keys()) - excluded, key=int)
    if len(paired_ids) < 2:
        raise RuntimeError(f"Expected matched image/label pairs, found {len(paired_ids)}.")
    if count < 2:
        raise ValueError("count must be at least two for a train/validation split.")
    selected_ids = sorted(random.Random(seed).sample(paired_ids, min(count, len(paired_ids))), key=int)

    jobs = []
    for scene_id in selected_ids:
        for objects, subdir in (
            (images, "RGB-PanSharpen"),
            (labels, "geojson/buildings"),
        ):
            key, size = objects[scene_id]
            jobs.append((key, size, output / subdir / Path(key).name))

    with ThreadPoolExecutor(max_workers=8) as pool:
        transferred = list(pool.map(lambda job: _download(*job), jobs))
    selected_bytes = sum(size for _, size, _ in jobs)
    transferred_bytes = sum(size for (_, size, _), was_downloaded in zip(jobs, transferred) if was_downloaded)

    manifest = {
        "dataset": "SpaceNet 2 AOI 2 Vegas building detection training data",
        "source": BUCKET_URL,
        "image_prefix": IMAGE_PREFIX,
        "label_prefix": LABEL_PREFIX,
        "license": "CC BY-SA 4.0",
        "seed": seed,
        "excluded_scene_ids": sorted(excluded, key=int),
        "requested_pairs": count,
        "downloaded_pairs": len(selected_ids),
        "scene_ids": selected_ids,
        "selected_image_and_label_bytes": selected_bytes,
        "transferred_bytes_this_run": transferred_bytes,
        "selected_data_mib": round(selected_bytes / (1024**2), 2),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/spacenet"))
    parser.add_argument("--count", type=int, default=48, help="Number of matched image/label scenes to fetch")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--exclude-manifest", type=Path, help="Download manifest whose scene IDs must be excluded")
    args = parser.parse_args()
    excluded = set()
    if args.exclude_manifest:
        excluded = set(json.loads(args.exclude_manifest.read_text(encoding="utf-8"))["scene_ids"])
    print(json.dumps(download_subset(args.output, count=args.count, seed=args.seed, exclude_ids=excluded), indent=2))


if __name__ == "__main__":
    main()
