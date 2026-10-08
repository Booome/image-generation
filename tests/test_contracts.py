"""第 6 轮守门器：跨文件契约一致性（只保留能自动判定的项）。

标 [info] 的是"需要人看一眼"的提示，不计入失败——把模糊判断硬编码成正则
只会制造误报，误报多了守门器就没人信了。
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SK = Path(r"C:\Users\bodon\workspace\zero-protocol\.opencode\skills\image-generation")
SCRIPTS = SK / "scripts"
REFS = SCRIPTS.parent / "references" / "providers"
hard, info = [], []


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = load("generate")

print("=== 1) 每个 provider 都有档案，且默认模型 / 环境变量都能在档案里找到 ===")
for prov, cfg in gen.PROVIDERS.items():
    doc = REFS / (prov + ".md")
    if not doc.exists():
        hard.append("provider %s 没有档案 %s" % (prov, doc.name))
        continue
    text = doc.read_text(encoding="utf-8")
    for m in {cfg["default_model"], *((cfg.get("models") or {}).keys())}:
        if m not in text:
            hard.append("%s: 模型 %s 未出现在 %s" % (prov, m, doc.name))
    if cfg["env_key"] not in text:
        hard.append("%s: 环境变量 %s 未出现在档案" % (prov, cfg["env_key"]))

print("=== 2) PROVIDERS 字段都被代码读取（未被读的字段 = 死配置）===")
src = (SCRIPTS / "generate.py").read_text(encoding="utf-8")
read_keys = set(re.findall(r'provider\.get\("([a-z_]+)"', src))
read_keys |= set(re.findall(r'provider\["([a-z_]+)"\]', src))
read_keys |= set(re.findall(r'cfg\.get\("([a-z_]+)"', src))
# 这些是数据，由 resolve_provider 整体合并后使用，无需逐个 get
DATA_KEYS = {"base", "env_key", "generations_path", "edits_path", "edit_format", "response",
             "default_model", "default_quality", "n_max", "size_rules", "common_sizes", "doc",
             "preflight_path", "models", "extra_params", "ref_field", "max_refs",
             "warn_ref_bytes", "max_ref_bytes"}
declared = set()
for cfg in gen.PROVIDERS.values():
    declared |= set(cfg)
    for ov in (cfg.get("models") or {}).values():
        declared |= set(ov)
for k in sorted(declared - read_keys - DATA_KEYS):
    hard.append("PROVIDERS 字段 '%s' 定义了但代码从不读取" % k)

print("=== 3) [info] 规则集数值 vs 档案口径（人工核对项）===")
for rule_name, rule in gen.SIZE_RULES.items():
    owners = [p.name for p in REFS.glob("*.md") if rule_name in p.read_text(encoding="utf-8")]
    if not owners:
        info.append("size_rules '%s' 没有档案提到" % rule_name)
    else:
        info.append("size_rules '%s' 用于 %s；请人工确认档案里的像素窗/边长口径与 %s 一致"
                    % (rule_name, ", ".join(owners), rule))

print("=== 4) 测试引用的脚本都存在 ===")
for tfile in (SK / "tests").glob("*.py"):
    for ref in re.findall(r'"([a-z_/]+\.py)"', tfile.read_text(encoding="utf-8")):
        name = Path(ref).name
        if name.endswith("_mut.py"):
            continue  # written to a temp dir at runtime
        if not (SCRIPTS / name).exists() and not (SK / "tests" / name).exists():
            hard.append("%s 引用了不存在的文件 %s" % (tfile.name, ref))

print("=== 5) 测试产物确实被 git 忽略 ===")
repo = SK.parents[2]
for pattern in ("node_modules", "__pycache__"):
    r = subprocess.run(["git", "check-ignore", "-q", str(SK / "tests" / pattern)],
                       capture_output=True, cwd=str(repo))
    if r.returncode != 0:
        hard.append("%s 未被 git 忽略" % pattern)

print("=== 6) scripts/ 与 SKILL.md 清单一致 ===")
actual = {p.name for p in SCRIPTS.glob("*.py")}
documented = set(re.findall(r"`([a-z_]+\.py)`", (SK / "SKILL.md").read_text(encoding="utf-8")))
for name in sorted(actual - documented):
    hard.append("scripts/%s 未在 SKILL.md 说明" % name)
for name in sorted(documented - actual):
    hard.append("SKILL.md 提到 scripts/%s 但不存在" % name)


print("=== 7) 入库文件不含真实本机绝对路径（AGENTS.md 永久规则）===")
# Verdict rule (straight from AGENTS.md): the segment right after `Users\` must
# start with `<`. Anything else is somebody's real home directory. Self-tested
# below so this guard cannot quietly rot into a no-op.
USERPATH = re.compile(r"(?:[A-Za-z]:[\\/]+Users|(?<![\w.])/(?:home|Users))[\\/]+([^\\/\s\"'`]+)")
PLACEHOLDER_TEST = [
    ("placeholder <you> passes", r"See <盘符>:\Users\<you>\AppData for details", True),
    ("placeholder <某人> passes", r"path is C:\Users\<某人>\x", True),
    ("real user name fails", r"root C:\Users\bodon\workspace", False),
    ("forward slashes fail", "home /Users/someone/proj", False),
    ("posix /home fails", "config at /home/alice/.config", False),
    ("url-ish text passes", "see https://example.com/Users/guide for docs", True),
    ("plain text passes", "no path here at all", True),
]
for label, sample, should_pass in PLACEHOLDER_TEST:
    found = [m.group(1) for m in USERPATH.finditer(sample) if not m.group(1).startswith("<")]
    ok = (not found) == should_pass
    if not ok:
        hard.append("路径守门器自检失败: %s -> %s" % (label, found))

repo = SK.parents[2]
tracked = [f for f in subprocess.run(["git", "ls-files", "-z"], capture_output=True,
           cwd=str(repo)).stdout.decode("utf-8").split(chr(0)) if f]
# This file carries deliberately-bad samples for the self-test above; scanning
# its own source would always flag them. Skip it and keep the samples honest.
SELF = "tests/test_contracts.py"
for f in tracked:
    if f.startswith("资产/待整理/") or f.endswith(SELF):
        continue
    full = repo / f
    if not full.is_file():
        continue
    try:
        text = full.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in USERPATH.finditer(line):
            if not m.group(1).startswith("<"):
                hard.append("%s L%d: 真实用户路径 Users/%s" % (f, lineno, m.group(1)))

print("=== 8) 测试脚本建临时目录后自清（不留垃圾）===")
for tf in sorted((SK / "tests").glob("test_*.py")):
    body = tf.read_text(encoding="utf-8")
    if "mkdtemp" in body and "atexit" not in body:
        hard.append("%s 用了 mkdtemp 但没注册回收（会往 %%TEMP%% 堆垃圾）" % tf.name)

for i in info:
    print("  [info] " + i)
for h in hard:
    print("  *** " + h)
print("hard issues: %d, info: %d" % (len(hard), len(info)))
sys.exit(1 if hard else 0)
