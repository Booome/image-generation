"""Convert the asset library's raster images to high-quality JPEG (q95).

Kept deliberately dumb so the result is auditable:
  * only extensions listed in SRC_EXT are touched, never .jpg/.jpeg
  * a sibling .jpg with the same stem is written/replaced only when it looks
    like a product of this run or is newer than the source; a PRE-EXISTING older
    .jpg is skipped unless --overwrite is passed
  * originals are left in place unless --delete-originals is passed
  * symlinks are re-pointed at the new .jpg (they are recreated locally)

Each output line is tagged NEW (fresh .jpg), OVER (replaced an existing one) or
SKIP. The overwrite guard is a heuristic: it compares mtimes, so a source whose
mtime was refreshed by a sync tool, or an old .jpg that IS this .png's previous
output, can be classified wrongly - hence the explicit --overwrite escape hatch.

Usage:
    python convert_assets_to_jpg.py --root <asset-dir> [--quality 95] [--dry-run]
                                    [--overwrite] [--delete-originals] [--skip <dirname>]
"""
import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

SRC_EXT = {".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

sys.stdout.reconfigure(encoding="utf-8")


def flatten(im):
    """RGBA/LA/P-with-transparency onto white; everything else to RGB."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace a pre-existing older sibling .jpg (default: skip it)")
    ap.add_argument("--delete-originals", action="store_true")
    ap.add_argument("--skip", action="append", default=[], help="directory name to skip")
    args = ap.parse_args()

    root = Path(args.root)
    todo = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in SRC_EXT:
            continue
        if any(part in args.skip for part in path.relative_to(root).parts):
            continue
        todo.append(path)

    total_in = total_out = 0
    converted = []
    counts = {"new": 0, "overwrite": 0, "skipped": 0}
    for path in todo:
        dst = path.with_suffix(".jpg")
        if dst.exists() and not args.overwrite:
            try:
                older = dst.stat().st_mtime < path.stat().st_mtime
            except OSError:
                older = True
            if older:
                counts["skipped"] += 1
                print("  %-46s SKIP  (existing .jpg older than source; --overwrite to replace)"
                      % str(path.relative_to(root)))
                continue
        status = "OVER" if dst.exists() else "NEW"
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                rgb = flatten(im)
                if not args.dry_run:
                    rgb.save(dst, "JPEG", quality=args.quality, optimize=True, subsampling=0)
        except OSError as exc:
            counts["skipped"] += 1
            print("  SKIP %-46s %s" % (path.name, exc))
            continue

        in_bytes = path.stat().st_size
        out_bytes = dst.stat().st_size if not args.dry_run else 0
        total_in += in_bytes
        total_out += out_bytes
        converted.append((path, dst, in_bytes, out_bytes, rgb.size))
        counts["overwrite" if status == "OVER" else "new"] += 1
        print("  %-46s %6.2fMB -> %6.2fMB  %dx%d  %s %s" % (
            str(path.relative_to(root)), in_bytes / 1048576,
            out_bytes / 1048576 if out_bytes else 0, rgb.size[0], rgb.size[1],
            status, "DRY" if args.dry_run else ""))

    print("converted %d files: %.2fMB -> %.2fMB (%.0f%% smaller)  [new %d / overwrite %d / skipped %d]" % (
        len(converted), total_in / 1048576, total_out / 1048576,
        (1 - total_out / total_in) * 100 if total_in and total_out else 0,
        counts["new"], counts["overwrite"], counts["skipped"]))

    if args.delete_originals and not args.dry_run:
        removed = 0
        for path, _, _, _, _ in converted:
            path.unlink()
            removed += 1
        print("deleted %d originals" % removed)

    # Re-point symlinks at the new .jpg siblings: an existing link whose target
    # was converted now points at a file we are about to drop.
    links = [p for p in root.rglob("*") if p.is_symlink()]
    relinked = []
    for link in links:
        target = (link.parent / os.readlink(link)).resolve()
        if target.suffix.lower() in SRC_EXT:
            new_target = target.with_suffix(".jpg")
            if new_target.exists():
                relinked.append((link, os.readlink(link), os.path.relpath(
                    new_target, link.parent).replace(os.sep, "/")))

    print("symlinks to re-point: %d" % len(relinked))
    for link, old, new in relinked:
        print("  %s : %s -> %s" % (link.relative_to(root), old, new))
        if not args.dry_run:
            link.unlink()
            os.symlink(new, link)


if __name__ == "__main__":
    main()
