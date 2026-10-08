#!/usr/bin/env python3
"""Convert a mask_editor PNG into Seedream normalized edit coordinates.

The mask (selected area = transparent alpha) yields a bounding box in pixels;
this script maps it to the 0-999 normalized form Seedream writes into the prompt:
`Image N x1 y1 x2 y2`.

Usage:
  python bbox_from_mask.py --mask <mask.png> [--image-index 1] [--image-size WxH]
Prints the pixel bbox and the ready-to-paste prompt token.
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image

ALPHA_SELECTED_MAX = 128  # alpha below this counts as selected


def parse_size(spec):
    try:
        w, h = re.split(r"[xX]", spec)
        w, h = int(w), int(h)
    except (ValueError, AttributeError):
        sys.exit(f"--image-size must look like 2816x1584 (got {spec!r})")
    if w <= 0 or h <= 0:
        sys.exit(f"--image-size edges must be positive (got {spec!r})")
    return w, h


def main():
    ap = argparse.ArgumentParser(description="mask PNG -> Seedream normalized bbox")
    ap.add_argument("--mask", required=True, help="mask PNG from mask_editor (selected = transparent)")
    ap.add_argument("--image-index", type=int, default=1, help="reference image number in the prompt (default 1)")
    ap.add_argument("--image-size", default=None,
                    help="optional WxH to override the mask's own size (must match the source image)")
    args = ap.parse_args()

    path = Path(args.mask)
    if not path.exists():
        sys.exit(f"mask not found: {args.mask}")

    mask = Image.open(path).convert("RGBA")
    w, h = mask.size
    if args.image_size:
        iw, ih = parse_size(args.image_size)
        if (iw, ih) != (w, h):
            sys.exit(
                f"--image-size {iw}x{ih} does not match the mask size {w}x{h}; "
                "pass the mask of the target image instead of resizing"
            )

    alpha = mask.getchannel("A")
    bbox = alpha.point(lambda v: 255 if v < ALPHA_SELECTED_MAX else 0).getbbox()
    if not bbox:
        sys.exit("no selected area found (nothing transparent in the mask)")

    x1, y1, x2, y2 = bbox
    # getbbox() returns x2/y2 exclusive; keep them inclusive for the coordinate token
    x2, y2 = x2 - 1, y2 - 1
    nx1, ny1 = round(x1 / w * 1000), round(y1 / h * 1000)
    nx2, ny2 = round(x2 / w * 1000), round(y2 / h * 1000)

    print(f"image size       : {w} x {h}")
    print(f"bbox pixels      : {x1} {y1} {x2} {y2}  ({x2 - x1 + 1} x {y2 - y1 + 1})")
    print(f"normalized 0-999 : {nx1} {ny1} {nx2} {ny2}")
    print(f"prompt token     : Image {args.image_index} {nx1} {ny1} {nx2} {ny2}")


if __name__ == "__main__":
    main()
