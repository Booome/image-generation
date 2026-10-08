"""第 7 轮：数据正确性 —— 文件内容与声明的元数据是否真的一致。"""
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

SK = Path(__file__).resolve().parents[1]
REPO = SK.parents[2]
ASSETS = REPO / "资产"
issues = []


def note(m):
    issues.append(m)
    print("  *** " + m)


print("=== 1) 资产库里的 jpg 都是真 JPEG，且尺寸可读 ===")
jpgs = [p for p in ASSETS.rglob("*.jpg") if p.is_file() and not p.is_symlink()]
pngs = [p for p in ASSETS.rglob("*.png") if p.is_file() and not p.is_symlink()]
print("  真身 jpg=%d  png=%d" % (len(jpgs), len(pngs)))
for p in jpgs:
    with open(p, "rb") as fh:
        magic = fh.read(2)
    if magic != b"\xff\xd8":
        note("%s 扩展名是 .jpg 但内容不是 JPEG" % p.relative_to(ASSETS))
checkable = 0
for p in jpgs:
    try:
        with Image.open(p) as im:
            im.verify()
        checkable += 1
    except Exception as exc:
        note("%s 无法解码: %s" % (p.relative_to(ASSETS), exc))
print("  可解码 %d/%d" % (checkable, len(jpgs)))

print("=== 2) 软链接：目标后缀 == 链接名后缀，且都能读 ===")
links = [p for p in ASSETS.rglob("*") if p.is_symlink()]
for p in links:
    target = os.readlink(p)
    t_ext = Path(target).suffix.lower()
    if t_ext != p.suffix.lower():
        note("%s(%s) -> %s 后缀不一致" % (p.relative_to(ASSETS), p.suffix, target))
    if not p.exists():
        note("%s 目标不存在" % p.relative_to(ASSETS))
print("  软链接 %d 条，全部可读=%s" % (len(links), all(p.exists() for p in links)))

print("=== 3) README/文档里承诺的命名规范 vs 实际文件名 ===")
import re
readme = (ASSETS / "README.md").read_text(encoding="utf-8")
id_pat = re.compile(r"^(chr|prp|vhl|mob|scn|gfx|wrn)-\d{6}\.(png|jpg|jpeg|webp)$")
# 生成参考/ 按自己的规范命名（6 位归一化数字），待整理/ 是未编号草稿：
# 两者都不参与分类编号，不能按 <code>-<6位> 规则查。
NON_ASSET_DIRS = {"待整理", "生成参考", "参考"}
for p in ASSETS.iterdir():
    if p.is_dir() and p.name not in NON_ASSET_DIRS:
        for f in p.iterdir():
            if f.is_file() and not f.is_symlink() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                if not id_pat.match(f.name):
                    note("分类目录下文件名不符 <code>-<6位>.<ext>: %s" % f.relative_to(ASSETS))
    elif p.is_dir() and p.name == "生成参考":
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg"):
                stem = f.stem
                if not (len(stem) == 6 and stem.isdigit()):
                    note("生成参考 文件名不符 6 位归一化: %s" % f.name)
            elif f.is_file():
                note("生成参考 里有非 JPG 文件: %s" % f.name)

print("=== 4) 资产/尺寸基准.md 若存在，其数值是否仍成立 ===")
bench = ASSETS / "尺寸基准.md"
if bench.exists():
    text = bench.read_text(encoding="utf-8")
    print("  （存在，%d 字；人工核对）" % len(text))
else:
    print("  （不存在，跳过）")

print("=== 5) .result.json 侧车是否只在 待整理/（不该混进资产分类目录）===")
for p in ASSETS.rglob("*.result.json"):
    if "待整理" in str(p): continue
    note("分类目录里混入侧车: %s" % p.relative_to(REPO))

print("=== 6) git 是否会提交 待整理/ ===")
r = subprocess.run(["git", "check-ignore", "-q", "资产/待整理/x.png"], cwd=str(REPO), capture_output=True)
print("  待整理 被忽略:", r.returncode == 0)
if r.returncode != 0:
    note("资产/待整理/ 未被忽略（README 铁律说它不提交）")

print("=== 7) 本次转换前后：入库图片的数量与体积 ===")
tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True).stdout.decode("utf-8").split("\n")
tracked_imgs = [f for f in tracked if f.startswith("资产/") and Path(f).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
tot = sum((REPO / f).stat().st_size for f in tracked_imgs if (REPO / f).is_file())
print("  入库图片 %d 个，合计 %.2f MB" % (len(tracked_imgs), tot / 1048576))

print("issues:", len(issues))
sys.exit(1 if issues else 0)
