"""第 9 轮：资源与清理（测试有没有留下垃圾 / 失败路径干不干净）。"""
import os
import shutil
import socket
import atexit
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SK = Path(__file__).resolve().parents[1]
REPO = SK
TESTS = SK / "tests"
issues = []


def note(m):
    issues.append(m)
    print("  *** " + m)


print("=== 1) 测试是否在 %TEMP% 堆积（run 完应自清）===")
# Run ONE leaf test, not run_e2e: run_e2e's offline group includes this file,
# so calling it here would recurse forever.
before = {p for p in Path(tempfile.gettempdir()).glob("*") if p.is_dir()}
r = subprocess.run([sys.executable, str(TESTS / "test_generate.py")],
                   capture_output=True, text=True, encoding="utf-8", cwd=str(REPO), timeout=120)
after = {p for p in Path(tempfile.gettempdir()).glob("*") if p.is_dir()}
leaked = sorted(p.name for p in (after - before))
print("  test_generate.py exit =", r.returncode)
print("  新增临时目录:", leaked or "none")
dirty = [n for n in leaked if n.startswith(("mut_", "req_", "assets_", "gen_unit_", "sem_"))]
if dirty:
    note("测试留下未清理的临时目录: %s" % dirty)

print("=== 2) 测试是否在仓库工作区留下文件 ===")
g = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                   encoding="utf-8", cwd=str(REPO))
untracked = []
if g.returncode == 0:
    untracked = [l[3:] for l in g.stdout.splitlines() if l.startswith("??")]
junk = [u for u in untracked if any(k in u for k in ("_mut", "_tmp", "mask_out", "e2e_mask", ".pyc"))]
print("  未跟踪项:", len(untracked), "其中疑似测试残留:", junk or "none")
if junk:
    note("测试残留进了工作区: %s" % junk)

print("=== 3) 端口是否都释放（测试起的 server 应退出）===")
for port in (8765, 8766, 8767, 8799):
    with socket.socket() as s:
        s.settimeout(0.3)
        busy = s.connect_ex(("127.0.0.1", port)) == 0
    print("  port %-5d %s" % (port, "OCCUPIED" if busy else "free"))
    if busy:
        note("端口 %d 仍被占用（server 没退）" % port)

print("=== 4) 失败路径：image 不存在时应 exit 1 而不是 traceback ===")
_fail_dir = Path(tempfile.mkdtemp(prefix="fail_"))
atexit.register(shutil.rmtree, _fail_dir, True)
_missing = _fail_dir / "nope.png"
_out = _fail_dir / "o.jpg"
r = subprocess.run([sys.executable, str(SK / "scripts" / "generate.py"), "--provider", "heyroute",
                    "--model", "gpt-image-2", "--size", "16:9 1K", "--prompt", "x",
                    "--image", str(_missing), "--out", str(_out)],
                   capture_output=True, text=True, encoding="utf-8", timeout=120)
combined = (r.stdout or "") + (r.stderr or "")
if "Traceback" in combined:
    note("失败路径抛了裸 traceback")
if r.returncode != 1:
    note("失败路径 exit 应为 1，实际 %d" % r.returncode)

print("=== 5) mutation_check 的临时副本是否清干净（慢，默认跳过）===")
# mutation_check runs every suite 10 times; only do that when explicitly asked,
# otherwise this file would dominate run_e2e's runtime.
if os.environ.get("RUN_MUTATION_HYGIENE") == "1":
    before_mut = {p for p in REPO.rglob("mut_*") if p.is_dir()}
    r = subprocess.run([sys.executable, str(TESTS / "mutation_check.py")],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(REPO), timeout=900)
    after_mut = {p for p in REPO.rglob("mut_*") if p.is_dir()}
    leftover = sorted(str(p.relative_to(REPO)) for p in (after_mut - before_mut))
    print("  mutation_check exit =", r.returncode, "| 残留副本:", leftover or "none")
    if leftover:
        note("mutation_check 留下副本: %s" % leftover)
else:
    print("  skipped (set RUN_MUTATION_HYGIENE=1 to include)")

print("issues:", len(issues))
sys.exit(1 if issues else 0)
