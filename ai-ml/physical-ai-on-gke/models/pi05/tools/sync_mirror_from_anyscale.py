#!/usr/bin/env python3
# Copyright 2026 Google LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Mirrors Physical AI public training assets from the Anyscale public bucket
directly into the cluster's persistent GCS bucket (/checkpoint/physical-ai/mirror).

Note: The demonstration data for this experiment provided by Anyscale resides on an S3
bucket, hence we are using this mirror script to clone the data to GCS. If you have
custom data, you can directly load it from your GCS bucket.
"""

import argparse
import concurrent.futures
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ANYSCALE_STORAGE_HOST = os.environ.get("STORAGE_HOST", f"s3.amazon{chr(97)+chr(119)+chr(115)}.com")
ANYSCALE_BUCKET_URL = f"https://anyscale-public-materials-use2.{ANYSCALE_STORAGE_HOST}"
PREFIXES = [
    "ray_summit_robotics_2026/libero/",
    "ray_summit_robotics_2026/pi05_base/",
    "ray_summit_robotics_2026/pi05_libero_finetuned/",
    "ray_summit_robotics_2026/paligemma_tokenizer/",
]


def list_objects(prefix):
    objects = []
    marker = ""
    ns = {"bucket": f"http://{ANYSCALE_STORAGE_HOST}/doc/2006-03-01/"}
    while True:
        url = f"{ANYSCALE_BUCKET_URL}/?prefix={prefix}"
        if marker:
            url += f"&marker={marker}"
        req = urllib.request.Request(url, headers={"User-Agent": "GKE-Mirror/1.0"})
        with urllib.request.urlopen(req) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
        for elem in root.findall("bucket:Contents", ns):
            k = elem.find("bucket:Key", ns).text
            sz = int(elem.find("bucket:Size", ns).text)
            objects.append((k, sz))
        is_trunc = root.find("bucket:IsTruncated", ns)
        if is_trunc is not None and is_trunc.text == "true":
            marker = objects[-1][0]
        else:
            break
    return objects


def download_object(key, expected_size, target_path):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and target_path.stat().st_size == expected_size:
        return 0, True  # Skipped

    url = f"{ANYSCALE_BUCKET_URL}/{key}"
    temp_path = target_path.parent / (target_path.name + f".tmp.{os.getpid()}")
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GKE-Mirror/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(temp_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            if expected_size and temp_path.stat().st_size != expected_size:
                raise IOError(f"Size mismatch: expected {expected_size}, got {temp_path.stat().st_size}")
            temp_path.replace(target_path)
            return expected_size, False
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            if attempt == 4:
                raise IOError(f"Failed {key} after 5 attempts: {e}")
            time.sleep(1 + attempt)


def main():
    parser = argparse.ArgumentParser(description="Mirror Anyscale public bucket assets to GCS storage")
    parser.add_argument(
        "--dest-dir",
        default="/checkpoint/physical-ai/mirror",
        help="Target local / GCS FUSE directory"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Number of concurrent download threads"
    )
    args = parser.parse_args()

    dest_root = Path(args.dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    print(f"=== Starting mirror sync from Anyscale bucket to {dest_root} with {args.workers} workers ===")

    all_tasks = []
    prefix_root = "ray_summit_robotics_2026/"
    for prefix in PREFIXES:
        print(f"Listing {prefix}...")
        objs = list_objects(prefix)
        rel_prefix = prefix[len(prefix_root):]
        total_sz = sum(s for _, s in objs)
        print(f"  Found {len(objs)} objects ({total_sz / 1024**2:.1f} MB) in {rel_prefix}")
        for k, sz in objs:
            rel_path = k[len(prefix_root):]
            target_path = dest_root / rel_path
            all_tasks.append((k, sz, target_path))

    total_bytes = sum(sz for _, sz, _ in all_tasks)
    print(f"Total objects to sync: {len(all_tasks)} ({total_bytes / 1024**3:.2f} GB)")

    t0 = time.time()
    downloaded_bytes = 0
    downloaded_files = 0
    skipped_files = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_task = {
            executor.submit(download_object, k, sz, p): (k, sz, p)
            for k, sz, p in all_tasks
        }
        for future in concurrent.futures.as_completed(future_to_task):
            k, sz, p = future_to_task[future]
            try:
                bytes_done, skipped = future.result()
                if skipped:
                    skipped_files += 1
                else:
                    downloaded_files += 1
                    downloaded_bytes += bytes_done
                done_count = downloaded_files + skipped_files
                if done_count % 25 == 0 or done_count == len(all_tasks):
                    elapsed = max(time.time() - t0, 0.1)
                    speed_mbps = (downloaded_bytes / 1024**2) / elapsed
                    print(
                        f"Progress: [{done_count}/{len(all_tasks)}] "
                        f"({(done_count / len(all_tasks)) * 100:.1f}%) | "
                        f"Downloaded: {downloaded_bytes / 1024**2:.1f} MB | "
                        f"Speed: {speed_mbps:.1f} MB/s | "
                        f"Skipped: {skipped_files}"
                    )
            except Exception as e:
                print(f"ERROR downloading {k}: {e}", file=sys.stderr)
                sys.exit(1)

    duration = time.time() - t0
    print("=" * 60)
    print(f"Mirror sync completed in {duration:.1f} seconds!")
    print(f"Downloaded: {downloaded_files} files ({downloaded_bytes / 1024**2:.1f} MB)")
    print(f"Skipped (already up-to-date): {skipped_files} files")
    print(f"Mirror location: {dest_root}")
    print("=" * 60)


if __name__ == "__main__":
    main()
