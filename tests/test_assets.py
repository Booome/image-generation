"""Offline tests for the asset/library helpers: compress_refs + convert_assets_to_jpg.

Both scripts touch real image files, so every case builds a throwaway tree.
Run: python tests/test_assets.py
"""
import atexit
import importlib.util
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
TMP = Path(tempfile.mkdtemp(prefix="assets_"))
atexit.register(shutil.rmtree, TMP, True)
fails = []


def check(name, cond, detail=""):
    print("  %-56s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_tree(root, spec):
    """spec: {relative_path: (mode, size, color_bytes)} -> returns created paths."""
    made = []
    for rel, (mode, size, color) in spec.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new(mode, size, color).save(p)
        made.append(p)
    return made


# ---------------------------------------------------------------- compress_refs
cr = load("compress_refs")
print("--- compress_refs: exact base64 length ---")
check("b64_len(0) == 0", cr.b64_len(0) == 0)
check("b64_len(1) == 4 (padded)", cr.b64_len(1) == 4)
check("b64_len(3) == 4 (no padding)", cr.b64_len(3) == 4)
check("b64_len(4) == 8", cr.b64_len(4) == 8)
check("b64_len matches base64 expansion", all(
    cr.b64_len(n) == len(__import__("base64").b64encode(b"\0" * n)) for n in range(0, 40)))

print("--- compress_refs: fitting shrinks to meet the budget ---")
work = TMP / "cr"
work.mkdir()
src = Image.new("RGB", (900, 700))
for x in range(900):                      # noise so JPEG cannot trivially compress
    for y in range(0, 700, 40):
        src.putpixel((x, y), ((x * 7) % 256, (y * 5) % 256, (x + y) % 256))
src_path = work / "noisy.png"
src.save(src_path)

im, orig = cr.load_rgb(src_path, 2048)
check("load_rgb caps the long edge (never upscales)", max(im.size) <= 2048, im.size)
check("load_rgb reports the original size", orig == (900, 700), orig)
check("load_rgb returns RGB", im.mode == "RGB", im.mode)

tight = 20_000
fitted, blobs, quality = cr.fit([im], tight, 95)
check("fit meets the tight budget", sum(cr.b64_len(len(b)) for b in blobs) <= tight,
      (sum(cr.b64_len(len(b)) for b in blobs), tight))
check("fit reports the quality it used", 1 <= quality <= 95, quality)
check("fit returns the images it encoded", fitted[0].size == im.size or fitted[0].size < im.size, fitted[0].size)

loose = 10_000_000
_, blobs_loose, q_loose = cr.fit([im], loose, 95)
check("fit leaves a generous budget at start quality", q_loose == 95, q_loose)

print("--- compress_refs: CLI writes jpg and reports the WRITTEN size ---")
out_dir = TMP / "cr_out"
r = subprocess.run([sys.executable, str(SCRIPTS / "compress_refs.py"), "--out-dir", str(out_dir),
                    "--target-bytes", "200000", "--quality", "95", str(src_path)],
                   capture_output=True, text=True, encoding="utf-8")
check("exit 0", r.returncode == 0, r.stderr[-200:])
written = sorted(out_dir.glob("*.jpg"))
check("wrote a .jpg", len(written) == 1, written)
if written:
    actual = Image.open(written[0]).size
    reported = r.stdout.split("->")[1].strip().split()[0]
    check("report matches the file on disk", reported == "%dx%d" % actual, (reported, actual))

r = subprocess.run([sys.executable, str(SCRIPTS / "compress_refs.py"), "--out-dir", str(out_dir),
                    "--target-bytes", "1000", "--quality", "60", str(src_path)],
                   capture_output=True, text=True, encoding="utf-8")
check("unreachable budget exits non-zero with a WARNING", r.returncode != 0 and "WARNING" in r.stderr,
      (r.returncode, r.stderr[-120:]))

r = subprocess.run([sys.executable, str(SCRIPTS / "compress_refs.py"), "--out-dir", str(out_dir),
                    str(TMP / "nope.png")], capture_output=True, text=True, encoding="utf-8")
check("missing input is refused", r.returncode != 0 and "not found" in (r.stderr + r.stdout))

# ---------------------------------------------------- convert_assets_to_jpg
conv = load("convert_assets_to_jpg")
print("--- convert_assets_to_jpg: only converts what it should ---")
tree = TMP / "lib"
created = make_tree(tree, {
    "images/img-000001.png": ("RGB", (120, 90), (10, 20, 30)),
    "images/img-000002.webp": ("RGB", (110, 80), (30, 40, 50)),
    "photos/keep.jpg": ("RGB", (100, 70), (60, 70, 80)),
    "skipme/scratch.png": ("RGB", (90, 60), (90, 10, 10)),
})

r = subprocess.run([sys.executable, str(SCRIPTS / "convert_assets_to_jpg.py"), "--root", str(tree),
                    "--skip", "skipme"], capture_output=True, text=True, encoding="utf-8")
check("exit 0", r.returncode == 0, r.stderr[-200:])
check("png converted", (tree / "images" / "img-000001.jpg").exists())
check("webp converted", (tree / "images" / "img-000002.jpg").exists())
check("skipped dir untouched", not (tree / "skipme" / "scratch.jpg").exists())
check("originals kept by default", (tree / "images" / "img-000001.png").exists())
check("existing .jpg not re-encoded", (tree / "photos" / "keep.jpg").exists())
check("partial-terminal-raster untouched", not list(tree.rglob("*.bmp")))
check("converted file is real JPEG", Image.open(tree / "images" / "img-000001.jpg").format == "JPEG")

print("--- convert_assets_to_jpg: symlinks follow their target ---")
link = tree / "images" / "extra-001.png"
link.unlink(missing_ok=True)
import os
os.symlink("img-000001.png", link)
r = subprocess.run([sys.executable, str(SCRIPTS / "convert_assets_to_jpg.py"), "--root", str(tree)],
                   capture_output=True, text=True, encoding="utf-8")
check("relink reported", "symlinks to re-point" in r.stdout, r.stdout[-160:])

print("--- convert_assets_to_jpg: --delete-originals, on a fresh tree ---")
tree2 = TMP / "lib2"
make_tree(tree2, {"a/b.png": ("RGB", (80, 60), (1, 2, 3)), "a/c.png": ("RGB", (80, 60), (4, 5, 6))})
r = subprocess.run([sys.executable, str(SCRIPTS / "convert_assets_to_jpg.py"), "--root", str(tree2),
                    "--delete-originals"], capture_output=True, text=True, encoding="utf-8")
check("exit 0", r.returncode == 0, r.stderr[-200:])
check("originals deleted", not list(tree2.rglob("*.png")))
check("jpgs exist", len(list(tree2.rglob("*.jpg"))) == 2)
check("'deleted 2 originals' reported", "deleted 2 originals" in r.stdout, r.stdout[-120:])

print("--- convert_assets_to_jpg: --dry-run changes nothing ---")
tree3 = TMP / "lib3"
make_tree(tree3, {"x.png": ("RGB", (50, 40), (9, 9, 9))})
before = sorted(p.name for p in tree3.rglob("*"))
r = subprocess.run([sys.executable, str(SCRIPTS / "convert_assets_to_jpg.py"), "--root", str(tree3),
                    "--dry-run"], capture_output=True, text=True, encoding="utf-8")
check("dry-run writes nothing", sorted(p.name for p in tree3.rglob("*")) == before, before)
check("dry-run still reports", "DRY" in r.stdout, r.stdout[-120:])

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
