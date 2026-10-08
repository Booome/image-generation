"""Offline unit tests for generate.py's local helpers (no network).

Covers: write_output format contract, image_size header parsing, configure_stdio
guards, and the size-rule helpers. Run: python tests/test_generate.py
"""
import atexit
import importlib.util
import shutil
import subprocess
import tempfile
import contextlib
import io
import os
import sys
from pathlib import Path

from PIL import Image

TESTS = Path(__file__).resolve().parent
GEN = TESTS.parent / "scripts" / "generate.py"

sys.stdout.reconfigure(encoding="utf-8")

spec = importlib.util.spec_from_file_location("gen", GEN)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

TMP = Path(tempfile.mkdtemp(prefix="gen_unit_"))
atexit.register(shutil.rmtree, TMP, True)
fails = []


def check(name, cond, detail=""):
    print("  %-52s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


def png(mode="RGB", size=(200, 120), color=(200, 30, 30)):
    b = io.BytesIO()
    Image.new(mode, size, color).save(b, "PNG")
    return b.getvalue()


def jpg(size=(200, 120), quality=92):
    b = io.BytesIO()
    Image.new("RGB", size, (10, 90, 200)).save(b, "JPEG", quality=quality)
    return b.getvalue()


def out(name):
    return TMP / name


print("--- write_output: format contract ---")
w, note = gen.write_output(png(), out("a.jpg"), 95)
check("RGB PNG source -> .jpg re-encodes", w.suffix == ".jpg" and w.read_bytes()[:2] == b"\xff\xd8", w)
check("  resolution preserved", gen.image_size(w) == (200, 120), gen.image_size(w))
w, note = gen.write_output(png(), out("b.jpg"), 60)
check("  lower --jpeg-quality shrinks the file", w.stat().st_size < gen.write_output(png(), out("b95.jpg"), 95)[0].stat().st_size)

raw = jpg()
w, note = gen.write_output(raw, out("c.jpg"), 95)
check("JPEG source -> .jpg writes bytes untouched", w.read_bytes() == raw, note)

w, note = gen.write_output(jpg(), out("d.png"), 95)
check("JPEG source -> .png writes bytes untouched, warns", w.read_bytes() == jpg() and note and "PNG" in note, note)

w, note = gen.write_output(png(), out("e.png"), 95)
check("PNG source -> .png untouched, silent", w.read_bytes() == png() and note is None, note)

w, note = gen.write_output(png("RGBA"), out("f.jpg"), 95)
check("alpha source -> falls back to .png", w.name == "f.png" and note and "alpha" in note, (w.name, note))
check("  alpha survives the fallback", Image.open(w).mode == "RGBA")

w, note = gen.write_output(png(), out("g"), 95)
check("extension-less --out becomes .jpg", w.name == "g.jpg" and w.exists(), w)

w, note = gen.write_output(png(), out("h.JPEG"), 95)
check(".JPEG (uppercase) also means JPEG", w.name == "h.JPEG" and w.read_bytes()[:2] == b"\xff\xd8", w)

print("--- write_output: unusable payloads die cleanly instead of raising ---")
# A header-valid but TRUNCATED stream is the case only im.load() can catch:
# Image.open() succeeds on the header alone, so without an explicit load() the
# truncation would sail through and be written out as a corrupt file.
good_png = png(size=(200, 120))
truncated_png = good_png[: len(good_png) // 3]

for label, raw in [
    ("empty bytes", b""),
    ("PNG magic only", b"\x89PNG\r\n\x1a\n"),
    ("HTML error page", b"<html><body>502 Bad Gateway</body></html>"),
    ("random bytes", bytes(range(256)) * 4),
    ("truncated PNG (header valid)", truncated_png),
]:
    target = out("bad_%s.jpg" % label.replace(" ", "_").replace("(", "").replace(")", ""))
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            gen.write_output(raw, target, 95)
            check("%s is refused" % label, False, "no exit")
        except SystemExit:
            check("%s is refused" % label, not target.exists(), target)
    check("%s explains itself" % label, "not a usable image" in err.getvalue(), err.getvalue()[:60])

print("--- image_size: header parsing ---")
check("PNG header", gen.image_size_bytes(png(size=(321, 77))) == (321, 77))
check("JPEG header", gen.image_size_bytes(jpg(size=(333, 88))) == (333, 88))
check("garbage -> None", gen.image_size_bytes(b"not an image at all") is None)
check("truncated PNG -> None", gen.image_size_bytes(png()[:12]) is None)

print("--- detect_format ---")
check("png magic", gen.detect_format(png()) == "png")
check("jpeg magic", gen.detect_format(jpg()) == "jpg")
check("unknown -> None", gen.detect_format(b"xxxx") is None)

print("--- configure_stdio: forces UTF-8 when piped, unless the env says otherwise ---")
# Runs in a CHILD process: only there is stdout a real pipe whose encoding the
# function can (and must) change. In-process assertions would be blind here.
def run_probe(env_extra):
    probe = (
        "import importlib.util,sys;"
        "spec=importlib.util.spec_from_file_location('g', %r);"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        "before=sys.stdout.encoding;m.configure_stdio();"
        "print(before,sys.stdout.encoding)"
    ) % str(GEN)
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    env.update(env_extra)
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=120)
    return (r.stdout or "").strip().split()


before, after = run_probe({})
check("piped stdout is switched to UTF-8", after == "utf-8", (before, after))
before, after = run_probe({"PYTHONIOENCODING": "gbk"})
check("an explicit PYTHONIOENCODING is left alone", after == "gbk", (before, after))

print("--- sidecar: the cataloguing draft, not run-time bookkeeping ---")
# The sidecar generate.py leaves next to the image is already a draft
# generation-parameter file: rename it and add an `asset` id / timestamp, and
# it is catalogable - with no hand transcription.
import json as _json

SIDECAR_KEYS = {"provider", "model", "endpoint", "requested_spec", "resolved_size",
                "actual_size", "quality", "n", "watermark", "reference_images", "mask", "prompt"}
RUN_ONLY_KEYS = {"status", "saved", "size_mismatch", "skill_update_suggested"}

work = Path(tempfile.mkdtemp(prefix="sidecar_"))
atexit.register(shutil.rmtree, work, True)
img = work / "ref.png"
Image.new("RGB", (40, 30), (7, 7, 7)).save(img)
out = work / "cand.jpg"

STUB = (
    "import importlib.util,sys,base64,io,json\n"
    "from PIL import Image\n"
    "spec=importlib.util.spec_from_file_location('g', %r)\n"
    "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
    "b=io.BytesIO();Image.new('RGB',(64,64),(1,2,3)).save(b,'PNG')\n"
    "PNG=base64.b64encode(b.getvalue()).decode()\n"
    "class R:\n"
    "    status_code=200\n"
    "    headers={'Content-Type':'application/json'}\n"
    "    text=json.dumps({'data':[{'b64_json':PNG}]})\n"
    "m.requests.post=lambda *a,**k: R()\n"
    "m.requests.get=lambda *a,**k: R()\n"
    "sys.argv=['g','--provider','volcengine','--model','doubao-seedream-5-0-pro-260628',"
    "'--size','16:9 1K','--prompt','SENTINEL PROMPT TEXT','--image',%r,'--out',%r]\n"
    "m.main()\n"
)
r = subprocess.run([sys.executable, "-c", STUB % (str(GEN), str(img), str(out))],
                   capture_output=True, text=True, encoding="utf-8", timeout=120,
                   env={**os.environ, "ARK_API_KEY": "test-key"})
check("stubbed run exits 0", r.returncode == 0, r.stderr[-300:])

side = out.with_suffix(".json")
check("sidecar sits beside the image, extension swapped", side.exists(), str(side))
if side.exists():
    text = side.read_text(encoding="utf-8")
    data = _json.loads(text)
    check("sidecar has exactly the cataloguing fields", set(data) == SIDECAR_KEYS,
          sorted(set(data) ^ SIDECAR_KEYS))
    check("sidecar carries no run-time keys", not (set(data) & RUN_ONLY_KEYS),
          sorted(set(data) & RUN_ONLY_KEYS))
    check("prompt is the full text", data.get("prompt") == "SENTINEL PROMPT TEXT", data.get("prompt"))
    check("reference_images recorded", data.get("reference_images") == [str(img)], data.get("reference_images"))
    check("sizes recorded", data.get("resolved_size") == "1824x1026" and data.get("actual_size") == "64x64",
          (data.get("resolved_size"), data.get("actual_size")))
    check("watermark captured from provider params", data.get("watermark") is False, data.get("watermark"))
    check("sidecar has no hardcoded user-home path beyond the temp fixture",
          text.count("C:\\\\Users\\\\") + text.count("C:/Users/") <= len(data.get("reference_images") or []),
          [l for l in text.splitlines() if "Users" in l][:3])

print("--- resolve_proxy: cli > env > profile ---")
pwork = Path(tempfile.mkdtemp(prefix="proxy_"))
atexit.register(shutil.rmtree, pwork, True)
(pwork / ".image-generation").mkdir()
(pwork / ".image-generation" / "profile.md").write_text(
    '---\nproxy: "http://prof:1"\n---\n', encoding="utf-8")
_cwd0 = os.getcwd()
os.chdir(pwork)
try:
    os.environ.pop("IMAGE_GENERATION_PROXY", None)
    check("profile proxy used", gen.resolve_proxy() == "http://prof:1", gen.resolve_proxy())
    os.environ["IMAGE_GENERATION_PROXY"] = "http://env:2"
    check("env beats profile", gen.resolve_proxy() == "http://env:2", gen.resolve_proxy())
    check("cli beats env", gen.resolve_proxy("http://cli:3") == "http://cli:3", gen.resolve_proxy("http://cli:3"))
finally:
    os.environ.pop("IMAGE_GENERATION_PROXY", None)
    os.chdir(_cwd0)

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
