"""Offline regression for generate.py size resolution + validation (no network).

Asserts the CONTRACT (ratio kept, contract-legal, invalid never substituted),
not today's literal numbers - a rule tweak must not turn these red.
"""
import contextlib
import importlib.util
import io
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SRC = Path(__file__).resolve().parents[1] / "scripts" / "generate.py"
spec = importlib.util.spec_from_file_location("gen", SRC)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

P = gen.PROVIDERS
fails = []


def check(name, cond, detail=""):
    print("  %-56s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


print("--- tiered specs: legal, right ratio, and honestly labelled ---")
for prov, spec_in, ratio in [
    ("heyroute", "16:9 1K", 16 / 9),
    ("heyroute", "16:9 4K", 16 / 9),
    ("heyroute", "3:2 4K", 3 / 2),
    ("infistar", "16:9 1K", 16 / 9),
    ("volcengine", "16:9 1K", 16 / 9),
    ("apiyi", "16:9 2K", 16 / 9),
    ("volcengine", "2176x1224", 16 / 9),
]:
    w, h, note = gen.resolve_size(spec_in, P[prov])
    rule = gen.SIZE_RULES[P[prov]["size_rules"]]
    check("%s %s: ratio %.4f" % (prov, spec_in, ratio), abs(w / h - ratio) < 0.01, w / h)
    check("%s %s: legal under its rule" % (prov, spec_in), gen._size_ok(w, h, rule),
          gen._explicit_errors(w, h, rule))
    # A size the provider ceiling had to pull in MUST say so - the caller has to
    # know it did not get the resolution it asked for.
    tier = re.search(r"(\d+)\s*[Kk]$", spec_in)
    clamped = "clamped" in (note or "")
    under_target = bool(tier) and min(w, h) < 1024 * int(tier.group(1)) * 0.95
    check("%s %s: clamp is disclosed" % (prov, spec_in), clamped == under_target,
          {"note": note, "min": min(w, h)})

print("--- explicit pixels pass through, invalid ones never get substituted ---")
for prov, spec_in in [("heyroute", "3840x2160"), ("volcengine", "2816x1584"), ("infistar", "3520x2336")]:
    w, h, _ = gen.resolve_size(spec_in, P[prov])
    try:
        gen.check_size_or_die(w, h, P[prov])
        check("%s %s accepted" % (prov, spec_in), True)
    except SystemExit:
        check("%s %s accepted" % (prov, spec_in), False, "wrongly rejected")

for prov, spec_in in [("heyroute", "bogus"), ("heyroute", "auto"), ("heyroute", "100x100"),
                      ("volcengine", "10000x10000"), ("apiyi", "16:9 1K")]:
    try:
        w, h, _ = gen.resolve_size(spec_in, P[prov])
        gen.check_size_or_die(w, h, P[prov])
        check("%s %s rejected" % (prov, spec_in), False, "unexpectedly accepted %dx%d" % (w, h))
    except SystemExit:
        check("%s %s rejected" % (prov, spec_in), True)

print("--- each rule fires on its OWN where the rule set allows it ---")
# Cases selected so exactly ONE rule rejects them - verified by these searches
# (see the comment on each row). If a check is deleted from _explicit_errors,
# its row stops being rejected and this block goes red.
#   pixel_window: 3552x2368 is ratio 1.5, under the edge cap, over max_px by
#     16866 - only the pixel window rejects it. (An odd edge like 1207x805 is
#     deliberately NOT here: edge-multiple is no longer validated.)
#   seedream_px (no edge rule, ratio cap 16): 1916x1916 is under max_edge and
#     ratio 1.0, and only the pixel floor rejects it.
SOLO = [
    ("pixel_window", 3552, 2368, "total pixels"),
    ("seedream_px", 1916, 1916, "total pixels"),
    ("seedream_pro_px", 956, 956, "total pixels"),
]
for rule_name, w, h, needle in SOLO:
    rule = gen.SIZE_RULES[rule_name]
    errs = gen._explicit_errors(w, h, rule)
    check("%s %dx%d: only the %r rule fires" % (rule_name, w, h, needle),
          len(errs) == 1 and needle in errs[0], errs)
    check("%s %dx%d: _size_ok agrees" % (rule_name, w, h), not gen._size_ok(w, h, rule), errs)

print("--- the remaining rules still reject at all (their sets make a solo case impossible) ---")
# In these rule sets max_edge**2 > max_px, so an over-long edge always also
# overflows the pixel window: a solo case cannot exist. Assert rejection only.
for rule_name, w, h, needle in [
    ("pixel_window", 4800, 800, "longest edge"),
    ("pixel_window", 4800, 800, "aspect ratio"),
    ("seedream_pro_px", 9000, 9000, "longest edge"),
    ("seedream_pro_px", 8192, 100, "aspect ratio"),
]:
    rule = gen.SIZE_RULES[rule_name]
    errs = gen._explicit_errors(w, h, rule)
    check("%s %dx%d: %r is reported" % (rule_name, w, h, needle), any(needle in e for e in errs), errs)
    check("%s %dx%d: _size_ok agrees" % (rule_name, w, h), not gen._size_ok(w, h, rule), errs)

print("--- rejections name the rule AND offer candidates ---")

print("--- rejections name the rule AND offer candidates ---")
buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    try:
        gen.check_size_or_die(100, 100, P["heyroute"])
    except SystemExit:
        pass
text = buf.getvalue()  # die() prints the report to stderr; exit() only carries the code
check("reports the violated rule", "total pixels" in text, text[:80])
check("offers nearest legal sizes", "official common size" in text)
check("states that nothing was sent", "no request was sent" in text)

print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)

