"""Mutation smoke test: break a script, confirm the suites go red.

A test that stays green when the code is wrong is not a test. Each mutation
names the file it targets, so coverage is not limited to generate.py.

Run: python mutation_check.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SK = Path(__file__).resolve().parents[1]
GEN = "scripts/generate.py"
REPO = SK.parents[2]

SUITES = ["test_generate.py", "test_sizes.py", "test_assets.py", "test_request.py",
          "test_contracts.py", "test_semantics.py"]

# (label, file under the skill, snippet to replace, replacement)
MUTATIONS = [
    ("generate: drop the max-edge check", GEN, 'if max(w, h) > rule["max_edge"]:', "if False:"),
    ("generate: drop the pixel-window check", GEN,
     'if px < rule["min_px"] or px > rule["max_px"]:', "if False:"),
    ("generate: drop the aspect-ratio check", GEN,
     'if w / h > rule["max_ratio"] or h / w > rule["max_ratio"]:', "if False:"),
    ("generate: always re-encode, even a JPEG source", GEN, 'if src != "jpg":', "if True:"),
    ("generate: ignore a .png request", GEN,
     'wants_png = out.suffix.lower() == ".png"', "wants_png = False"),
    ("generate: skip the payload usability guard", GEN,
     "im.load()  # truncated payloads only fail here, not on open()", "pass"),
    ("generate: ignore an explicit PYTHONIOENCODING", GEN,
     'if os.environ.get("PYTHONIOENCODING") or os.environ.get("PYTHONUTF8"):', "if False:"),
    ("generate: never recognise PNG", GEN,
     'if len(data) >= 24 and data[:8] == PNG_MAGIC and data[12:16] == b"IHDR":', "if False:"),
    ("generate: resolve_size forgets the tier clamp", GEN,
     'note += " (clamped down to provider limits)"', "pass"),

    ("mask_editor: break the transparent-alpha contract", "scripts/mask_editor.py",
     "id.data[i + 3] = s[i];", "id.data[i + 3] = 255;"),
    ("mask_editor: stop clearing the canvas before redraw", "scripts/mask_editor.py",
     "sctx.fillRect(0, 0, sel.width, sel.height);", "/* no-op */"),
    ("mask_editor: never write the mask server-side", "scripts/mask_editor.py",
     "out_path.write_bytes(img_bytes_out)", "pass"),

    ("bbox_from_mask: widen the alpha threshold", "scripts/bbox_from_mask.py",
     "ALPHA_SELECTED_MAX = 128", "ALPHA_SELECTED_MAX = 255"),
]


def run_browser(mutated_text, target):
    """For mask_editor mutations the verdict lives in the browser half."""
    work = Path(tempfile.mkdtemp(prefix="mutb_", dir=str(REPO)))
    try:
        skill = work / ".opencode" / "skills" / "image-generation"
        skill.parent.mkdir(parents=True)
        shutil.copytree(SK, skill, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        assets = work / "资产"
        try:
            assets.symlink_to(REPO / "资产", target_is_directory=True)
        except (OSError, NotImplementedError):
            shutil.copytree(REPO / "资产" / "场景", assets / "场景")
        (skill / target).write_text(mutated_text, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, str(skill / "tests" / "run_e2e.py")],
                               capture_output=True, text=True, encoding="utf-8", timeout=420)
            return {"browser-run_e2e": r}
        except subprocess.TimeoutExpired:
            return {"browser-run_e2e": type("R", (), {"returncode": -1})()}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_suites(mutated_text, target):
    """Run the suites against a mutated copy.

    The copy keeps the skill at the SAME depth inside a skeleton repo (with the
    资产/ tree linked in), because the tests resolve the repo by walking up from
    __file__ - a flat temp copy would lose that path.
    """
    work = Path(tempfile.mkdtemp(prefix="mut_", dir=str(REPO)))
    try:
        skill = work / ".opencode" / "skills" / "image-generation"
        skill.parent.mkdir(parents=True)
        shutil.copytree(SK, skill, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        assets = work / "资产"
        try:
            assets.symlink_to(REPO / "资产", target_is_directory=True)
        except (OSError, NotImplementedError):
            shutil.copytree(REPO / "资产" / "场景", assets / "场景")
        (skill / target).write_text(mutated_text, encoding="utf-8")
        out = {}
        for name in SUITES:
            try:
                out[name] = subprocess.run(
                    [sys.executable, str(skill / "tests" / name)],
                    capture_output=True, text=True, encoding="utf-8",
                    timeout=180)
            except subprocess.TimeoutExpired:
                out[name] = type("R", (), {"returncode": -1})()
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


baseline = run_suites((SK / GEN).read_text(encoding="utf-8"), GEN)
print("baseline:", ", ".join("%s=%d" % (n, r.returncode) for n, r in baseline.items()))
if any(r.returncode != 0 for r in baseline.values()):
    sys.exit("a suite is already red - fix that before mutating")

blind = []
for label, target, old, new in MUTATIONS:
    src = SK / target
    original = src.read_text(encoding="utf-8")
    mutated = original.replace(old, new, 1)
    if mutated == original:
        print("  %-52s SKIP (anchor not found in %s)" % (label, target))
        blind.append(label)
        continue
    res = run_browser(mutated, target) if "mask_editor" in target else run_suites(mutated, target)
    caught = [n for n, r in res.items() if r.returncode != 0]
    print("  %-52s %s" % (label, ("caught by " + ", ".join(caught)) if caught else "*** BLIND ***"))
    if not caught:
        blind.append(label)

print("blind spots:", len(blind), blind)
sys.exit(1 if blind else 0)
