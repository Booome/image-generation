"""Offline regression for generate.py request building (requests.post is stubbed).

No provider is contacted: the point is that the three request shapes carry the
right fields, types and endpoint before anything is billed.
"""
import atexit
import base64
import shutil
import tempfile
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

TESTS = Path(__file__).resolve().parent
SRC = TESTS.parent / "scripts" / "generate.py"
IMG = TESTS / "fixtures" / "sample.jpg"
if not IMG.exists():
    sys.exit("missing fixture %s (run tests/fixtures/make_fixtures.py)" % IMG)
TMP = Path(tempfile.mkdtemp(prefix="req_"))
atexit.register(shutil.rmtree, TMP, True)

spec = importlib.util.spec_from_file_location("gen", SRC)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

buf = io.BytesIO()
Image.new("RGB", (64, 64), (10, 20, 30)).save(buf, "PNG")
PNG_B64 = base64.b64encode(buf.getvalue()).decode()

cap = {}


class FakeResp:
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}
        self.status_code = 200

    @property
    def text(self):
        return json.dumps({"data": [{"b64_json": PNG_B64}]})


def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None, stream=False):
    cap.update(url=url, headers=headers, data=data, files=files, body=json, stream=stream)
    return FakeResp()


def fake_get(url, headers=None, timeout=None):
    return type("R", (), {"status_code": 200})()


gen.requests.post = fake_post
gen.requests.get = fake_get
# Offline test: no provider is contacted, so no real credential should be needed.
gen.read_env = lambda name: "test-key"

fails = []


def check(name, cond, detail=""):
    print("  %-42s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


def run(argv):
    cap.clear()
    sys.argv = ["generate.py"] + [str(a) for a in argv]
    gen.main()


print("--- A) edits branch (heyroute, single image, SSE) ---")
run(["--provider", "heyroute", "--model", "gpt-image-2", "--size", "1536x1024",
     "--quality", "high", "--prompt", "hello", "--image", IMG,
     "--out", str(TMP / "_rb_edits.jpg")])
check("url is /images/edits", cap["url"].endswith("/images/edits"), cap["url"])
check("multipart data fields", cap["data"] and cap["data"].get("n") == "1", cap["data"])
check("data carries model/prompt/size/quality",
      cap["data"].get("model") == "gpt-image-2" and cap["data"].get("prompt") == "hello"
      and cap["data"].get("size") == "1536x1024" and cap["data"].get("quality") == "high", cap["data"])
check("SSE stream flag is the string 'true'", cap["data"].get("stream") == "true", cap["data"])
check("files use repeated 'image' field", cap["files"] and cap["files"][0][0] == "image", cap["files"] and cap["files"][0][0])

print("--- B) generations branch (volcengine, text-to-image, JSON) ---")
run(["--provider", "volcengine", "--model", "doubao-seedream-5-0-pro-260628",
     "--size", "16:9 1K", "--prompt", "hello",
     "--out", str(TMP / "_rb_gen.jpg")])
check("url is /images/generations", cap["url"].endswith("/images/generations"), cap["url"])
check("json body n is the int 1", cap["body"] and cap["body"].get("n") == 1, cap["body"])
check("no quality key (provider default is None)", "quality" not in (cap["body"] or {}), cap["body"])
check("extra_params merged (watermark false)", cap["body"].get("watermark") is False, cap["body"])
check("size resolved for volcengine", cap["body"].get("size") == "1824x1026", cap["body"].get("size"))
check("no stream flag for JSON provider", "stream" not in (cap["body"] or {}), cap["body"])

print("--- C) json_images branch (apiyi, reference array) ---")
run(["--provider", "apiyi", "--model", "seedream-5-0-260128", "--size", "16:9 2K",
     "--prompt", "hello", "--image", IMG,
     "--out", str(TMP / "_rb_json.jpg")])
check("url is /images/generations", cap["url"].endswith("/images/generations"), cap["url"])
check("refs ride in the singular 'image' array",
      isinstance(cap["body"].get("image"), list) and cap["body"]["image"][0].startswith("data:image/"),
      cap["body"].get("image") and cap["body"]["image"][0][:30])
check("apiyi extra_params merged", cap["body"].get("watermark") is False
      and cap["body"].get("output_format") == "png", cap["body"])
check("no quality key for apiyi", "quality" not in cap["body"], cap["body"].get("quality"))

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
