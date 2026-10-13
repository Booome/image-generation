"""Offline regression for generate.py request building (requests.post is stubbed).

No provider is contacted: the point is that the three request shapes carry the
right fields, types and endpoint before anything is billed.
"""
import atexit
import base64
import contextlib
import shutil
import tempfile
import importlib.util
import io
import json
import sys
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


def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None, stream=False, proxies=None):
    cap.update(url=url, headers=headers, data=data, files=files, body=json, stream=stream, proxies=proxies)
    return FakeResp()


def fake_get(url, headers=None, timeout=None, proxies=None):
    cap["get_proxies"] = proxies
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
check("no proxy configured -> proxies is None", cap.get("proxies") is None, cap.get("proxies"))

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

print("--- D) --transparent: the native-alpha recipe and its local preconditions ---")
# Transparent mode is a MODEL capability, declared as transparent_params (recipe
# measured end to end - see references/providers/volcengine.md). Every
# precondition is local, so a mistake must cost nothing: four of the five
# scenarios below assert that no request was even built.
ALPHA_REF = TMP / "_alpha_ref.png"
Image.new("RGBA", (48, 36), (9, 9, 9, 0)).save(ALPHA_REF)


def run_expect_die(argv):
    """Run main() expecting die(); return (exit code, stderr text)."""
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            run(argv)
    except SystemExit as exc:
        return exc.code, err.getvalue()
    return None, err.getvalue()


run(["--provider", "volcengine", "--model", "doubao-seedream-5-0-pro-260628",
     "--size", "3:4 2K", "--prompt", "hello", "--image", ALPHA_REF,
     "--transparent", "--out", str(TMP / "_rb_trans.png")])
check("body carries background=transparent", cap["body"].get("background") == "transparent", cap["body"])
check("body carries output_format=png", cap["body"].get("output_format") == "png", cap["body"])
check("transparent overrides extra_params response_format",
      cap["body"].get("response_format") == "b64_json", cap["body"].get("response_format"))
check("watermark stays disabled alongside it", cap["body"].get("watermark") is False, cap["body"])
check("refs still ride in the singular 'image' array",
      isinstance(cap["body"].get("image"), list) and cap["body"]["image"][0].startswith("data:image/"),
      cap["body"].get("image") and cap["body"]["image"][0][:30])

BASE = ["--provider", "volcengine", "--model", "doubao-seedream-5-0-pro-260628",
        "--size", "3:4 2K", "--prompt", "hello"]
code, err = run_expect_die(BASE + ["--transparent", "--out", str(TMP / "_rb_noimg.png")])
check("refused without --image (image-to-image only)",
      code == 1 and "--image" in err and not cap, (code, err.strip()[-110:]))

code, err = run_expect_die(BASE + ["--transparent", "--image", IMG, "--out", str(TMP / "_rb_opa.png")])
check("refused when the input has no alpha channel",
      code == 1 and "alpha" in err and not cap, (code, err.strip()[-110:]))

code, err = run_expect_die(BASE + ["--transparent", "--image", ALPHA_REF,
                                   "--out", str(TMP / "_rb_trans.jpg")])
check("refused when --out is not .png",
      code == 1 and ".png" in err and not cap, (code, err.strip()[-110:]))

code, err = run_expect_die(["--provider", "heyroute", "--model", "gpt-image-2", "--size", "1536x1024",
                            "--prompt", "hello", "--image", ALPHA_REF,
                            "--transparent", "--out", str(TMP / "_rb_hey.png")])
check("refused on a model with no declared recipe",
      code == 1 and "not supported" in err and not cap, (code, err.strip()[-110:]))

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
