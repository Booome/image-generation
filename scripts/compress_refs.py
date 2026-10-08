#!/usr/bin/env python3
"""Re-encode reference images to fit a provider's base64 upload budget.

APIYi/Seedream takes references as base64 data URIs in the JSON body, so large
payloads time out on the cross-border hop (docs: keep multi-image base64 under
6 MB; >20 MB is a hard 400). This normalizes each image (EXIF orientation, RGB),
caps the long edge, encodes JPEG, then steps quality/scale down until the
estimated base64 total fits the target.

Usage:
  python compress_refs.py --out-dir <dir> img1.png img2.png ...
Prints a per-image report and the compressed paths (ready for --image).
"""
import argparse
import io
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

RESAMPLE = Image.Resampling.LANCZOS


def b64_len(n_bytes):
    """Exact base64 length (incl. padding) of an n-byte payload."""
    return (n_bytes + 2) // 3 * 4


def load_rgb(path, max_edge):
    """Open, orient, flatten to RGB, and cap the long edge (never upscales)."""
    im = Image.open(path)
    im.load()
    orig_size = im.size
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if max(im.size) > max_edge:
        scale = max_edge / max(im.size)
        im = im.resize(
            (max(1, round(im.width * scale)), max(1, round(im.height * scale))), RESAMPLE
        )
    return im, orig_size


def encode(im, quality):
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def fit(images, target_b64, start_quality):
    """Step quality down, then scale down, until the base64 total fits."""
    qualities = [q for q in (start_quality, 85, 80, 75, 70, 65, 60) if q <= start_quality]
    current = images
    for _ in range(4):
        for q in qualities:
            blobs = [encode(im, q) for im in current]
            if sum(b64_len(len(b)) for b in blobs) <= target_b64:
                return current, blobs, q
        current = [
            im.resize((max(1, round(im.width * 0.8)), max(1, round(im.height * 0.8))), RESAMPLE)
            for im in current
        ]
    return current, [encode(im, qualities[-1]) for im in current], qualities[-1]


def main():
    ap = argparse.ArgumentParser(description="Compress reference images to a base64 upload budget")
    ap.add_argument("images", nargs="+", help="input image paths")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: <temp>/image-generation/refs)")
    ap.add_argument("--max-edge", type=int, default=2048, help="long-edge cap (never upscales)")
    ap.add_argument("--quality", type=int, default=90, help="starting JPEG quality")
    ap.add_argument("--target-bytes", type=int, default=6 * 1024 * 1024,
                    help="base64 total budget (default 6 MB, the provider's recommended ceiling)")
    args = ap.parse_args()

    if args.max_edge < 16:
        sys.exit("--max-edge must be >= 16")
    if not 1 <= args.quality <= 95:
        sys.exit("--quality must be in 1..95")

    paths = [Path(p) for p in args.images]
    for p in paths:
        if not p.exists():
            sys.exit(f"image not found: {p}")

    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.gettempdir()) / "image-generation" / "refs"
    out_dir.mkdir(parents=True, exist_ok=True)

    loaded = [load_rgb(p, args.max_edge) for p in paths]
    images = [im for im, _ in loaded]
    images, blobs, quality = fit(images, args.target_bytes, args.quality)

    print("--- reference compression ---")
    total_in = total_out = total_b64 = 0
    outs = []
    used = {}
    for src, (_, orig_size), out_im, blob in zip(paths, loaded, images, blobs):
        in_bytes = src.stat().st_size
        total_in += in_bytes
        total_out += len(blob)
        total_b64 += b64_len(len(blob))
        stem = src.stem
        if stem in used:
            used[stem] += 1
            stem = "{}-{}".format(src.stem, used[stem])
        else:
            used[stem] = 0
        dst = out_dir / (stem + ".jpg")
        dst.write_bytes(blob)
        outs.append(dst)
        print("  {}: {}x{} {:.2f}MB -> {}x{} {:.2f}MB (q{})".format(
            src.name, orig_size[0], orig_size[1], in_bytes / 1048576,
            out_im.width, out_im.height, len(blob) / 1048576, quality))
    print("total: {:.2f}MB -> {:.2f}MB jpeg | est. base64 {:.2f}MB (target {:.2f}MB)".format(
        total_in / 1048576, total_out / 1048576, total_b64 / 1048576,
        args.target_bytes / 1048576))
    print("compressed paths:")
    for dst in outs:
        print("  {}".format(dst))
    if total_b64 > args.target_bytes:
        print(
            "WARNING: compressed total {:.2f}MB base64 still exceeds the {:.2f}MB target".format(
                total_b64 / 1048576, args.target_bytes / 1048576),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
