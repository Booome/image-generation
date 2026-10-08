"""第 8 轮：既有语义有无被我这几轮改动悄悄改掉（行为回归）。"""
import argparse
import importlib.util
import numpy as np
import io
import atexit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SK = Path(__file__).resolve().parents[1]
SCRIPTS = SK / "scripts"
issues = []


def note(m):
    issues.append(m)
    print("  *** " + m)


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


print("=== 1) mask_editor 保存语义没变：框内 alpha=0、框外 alpha=255（bbox 工具依赖它）===")
from PIL import Image, ImageDraw

sys.path.insert(0, str(SK / 'tests'))
spec = importlib.util.spec_from_file_location("me", SCRIPTS / "mask_editor.py")
me = importlib.util.module_from_spec(spec)
spec.loader.exec_module(me)
html = me.HTML
for must in ('id.data[i + 3] = s[i]', "fillStyle = '#fff'", "fillRect(0, 0, sel.width, sel.height)"):
    if must not in html:
        note("mask_editor 的关键保存/初始化代码不见了: %s" % must)

print("=== 2) bbox_from_mask 的契约没变：仍吃 alpha<128 的区域 ===")
bbox_src = (SCRIPTS / "bbox_from_mask.py").read_text(encoding="utf-8")
if "ALPHA_SELECTED_MAX = 128" not in bbox_src:
    note("bbox_from_mask 的阈值常量被改动了")

work = Path(tempfile.mkdtemp(prefix="sem_"))
atexit.register(shutil.rmtree, work, True)
m = Image.new("RGBA", (200, 100), (255, 255, 255, 255))
ImageDraw.Draw(m).rectangle((40, 20, 160, 80), fill=(255, 255, 255, 0))
mp = work / "m.png"
m.save(mp)
r = subprocess.run([sys.executable, str(SCRIPTS / "bbox_from_mask.py"), "--mask", str(mp)],
                   capture_output=True, text=True, encoding="utf-8")
print("  " + (r.stdout or "").strip().splitlines()[1] if r.stdout else "  (no output)")
if "40 20 160 80" not in (r.stdout or ""):
    note("bbox_from_mask 反解结果与我喂进去的矩形不符")

print("=== 3) generate.py 的 exit code 语义没变（die=1、成功=0）===")
gen = load("generate")
out = work / "x.jpg"
r = subprocess.run([sys.executable, str(SCRIPTS / "generate.py"), "--provider", "heyroute",
                    "--size", "bogus", "--prompt", "x", "--out", str(out)],
                   capture_output=True, text=True, encoding="utf-8")
if r.returncode != 1:
    note("参数错误应 exit 1，实际 %d" % r.returncode)

print("=== 4) --size 现在是必填（无默认），缺省即报错 ===")
r = subprocess.run([sys.executable, str(SCRIPTS / "generate.py"), "--provider", "heyroute",
                    "--prompt", "x", "--out", str(work / "x.jpg")],
                   capture_output=True, text=True, encoding="utf-8")
if r.returncode == 0 or "--size" not in (r.stderr or ""):
    note("缺少 --size 时应报错并点名 --size，实际 rc=%d" % r.returncode)

print("=== 5) compress_refs 的文件名去重语义没变 ===")
cr = load("compress_refs")
d = work / "cr"
d.mkdir()
for n in ("a.png", "a.jpg"):
    pass
imgs = []
for name in ("same.png", "same.jpg"):
    p = d / name
    Image.new("RGB", (60, 40), (9, 9, 9)).save(p)
out_dir = work / "cr_out"
r = subprocess.run([sys.executable, str(SCRIPTS / "compress_refs.py"), "--out-dir", str(out_dir),
                    str(d / "same.png"), str(d / "same.jpg")],
                   capture_output=True, text=True, encoding="utf-8")
written = sorted(p.name for p in out_dir.glob("*.jpg"))
print("  written:", written)
if len(written) != 2:
    note("同名不同扩展的两个输入应产出 2 个文件，实得 %d" % len(written))

print("=== 6) convert_assets_to_jpg 的默认行为没变（保留原图、只转指定扩展名）===")
tree = work / "lib"
(tree / "sub").mkdir(parents=True)
Image.new("RGB", (50, 40), (1, 2, 3)).save(tree / "sub" / "keep.jpg")
Image.new("RGB", (50, 40), (4, 5, 6)).save(tree / "sub" / "conv.png")
before_jpg = (tree / "sub" / "keep.jpg").read_bytes()
r = subprocess.run([sys.executable, str(SCRIPTS / "convert_assets_to_jpg.py"), "--root", str(tree)],
                   capture_output=True, text=True, encoding="utf-8")
if (tree / "sub" / "keep.jpg").read_bytes() != before_jpg:
    note("已有的 .jpg 被重编码了（应原样保留）")
if not (tree / "sub" / "conv.png").exists():
    note("默认应保留原图，实际被删了")

print("=== 7) mask_editor 的页面不允许被缓存（旧页面会让编辑器看起来失灵）===")
me = (SCRIPTS / "mask_editor.py").read_text(encoding="utf-8")
if "no-store" not in me:
    note("mask_editor 未发送 no-store：浏览器会缓存旧页面，工具改动后用户看到的还是老行为")

print("issues:", len(issues))
sys.exit(1 if issues else 0)
