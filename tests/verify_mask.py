"""Verify the mask produced by the E2E run (pixels + bbox_from_mask integration).

Usage: python verify_mask.py <mask.png> <source-image>
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

TESTS = Path(__file__).resolve().parent
BBOX_SCRIPT = TESTS.parent / "scripts" / "bbox_from_mask.py"

fails = []


def check(name, cond, detail=""):
    print("  %-46s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


mask_path, img_path = sys.argv[1], sys.argv[2]
if not Path(mask_path).exists():
    sys.exit("mask was never written: %s" % mask_path)
im = Image.open(mask_path).convert("RGBA")
src = Image.open(img_path)
alpha = im.getchannel("A")
W, H = im.size
print("mask %dx%d  src %dx%d" % (W, H, src.width, src.height))
check("mask matches source size", (W, H) == src.size, (W, H))

bbox = alpha.point(lambda v: 255 if v < 128 else 0).getbbox()
check("has a transparent region", bool(bbox), bbox)
if bbox:
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    # The E2E now ends on a BRUSH stroke (multi-selection support), so the final
    # mask is no longer "one 16:9 rectangle". Assert only what the contract
    # actually guarantees: a non-degenerate region that stays inside the image
    # and leaves its surroundings opaque.
    check("bbox is non-degenerate", bw > 2 and bh > 2, (bw, bh))
    check("bbox is inside the image", 0 <= x1 < x2 <= W and 0 <= y1 < y2 <= H, bbox)
    check("outside bbox is opaque",
          alpha.getpixel((2, 2)) == 255 and alpha.getpixel((W - 3, H - 3)) == 255,
          (alpha.getpixel((2, 2)), alpha.getpixel((W - 3, H - 3))))
    # Only invariants here: the E2E deliberately draws more than once, so the
    # painted area is not "one ellipse" any more - asserting an exact coverage
    # would encode the test script's drawing order instead of the contract.
    hist = alpha.histogram()
    frac = sum(hist[:128]) / (W * H)
    check("selection covers a sane fraction of the image", 0.0001 < frac < 0.5, "%.4f" % frac)

out = subprocess.run([sys.executable, str(BBOX_SCRIPT), "--mask", mask_path],
                     capture_output=True, text=True, encoding="utf-8")
print("  bbox_from_mask.py ->")
for line in (out.stdout or "").strip().splitlines():
    print("     " + line)
check("bbox_from_mask exits 0", out.returncode == 0, out.stderr)
check("prompt token produced", any(l.startswith("prompt token") for l in (out.stdout or "").splitlines()))

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
