"""Offline tests for generate.py's env / keys / profile resolution (no network).

Covers read_env precedence, the optional keys file, the project-profile
frontmatter parser, proxy resolution, and UTF-8 BOM tolerance. No provider is
contacted and no secret value is printed. Run: python tests/test_env.py
"""
import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TESTS = Path(__file__).resolve().parent
GEN = TESTS.parent / "scripts" / "generate.py"

spec = importlib.util.spec_from_file_location("gen", GEN)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

TMP = Path(tempfile.mkdtemp(prefix="env_unit_"))
atexit.register(shutil.rmtree, TMP, True)
fails = []

KEYS = "IMG_TEST_%d_KEY" % os.getpid()
_ENV_KEYS = ("IMAGE_GENERATION_KEYS_FILE", "IMAGE_GENERATION_PROFILE", "IMAGE_GENERATION_PROXY")
_SAVED = {k: os.environ.get(k) for k in _ENV_KEYS}
_SAVED_CWD = os.getcwd()


def clean_env():
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    os.environ.pop(KEYS, None)
    os.chdir(TMP)


def restore():
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.environ.pop(KEYS, None)
    os.chdir(_SAVED_CWD)


atexit.register(restore)


def check(name, cond, detail=""):
    print("  %-56s %s" % (name, "OK" if cond else "FAIL " + str(detail)))
    if not cond:
        fails.append(name)


(TMP / ".image-generation").mkdir(parents=True, exist_ok=True)

print("--- read_env: process env wins; empty does not shadow ---")
clean_env()
os.environ[KEYS] = "from-process"
check("process env value used", gen.read_env(KEYS) == "from-process", gen.read_env(KEYS))
os.environ[KEYS] = ""
(TMP / ".image-generation" / "keys.env").write_text("%s=from-file\n" % KEYS, encoding="utf-8")
check("empty process env falls through to keys file", gen.read_env(KEYS) == "from-file", gen.read_env(KEYS))
check("missing everywhere -> empty string", gen.read_env(KEYS + "_NOPE") == "", gen.read_env(KEYS + "_NOPE"))

print("--- keys file parsing ---")
clean_env()
kf = TMP / "custom.env"
kf.write_text("# a comment\n\n%s='quoted'\nOTHER=a=b\nNOEQUALS\n" % KEYS, encoding="utf-8")
os.environ["IMAGE_GENERATION_KEYS_FILE"] = str(kf)
check("single quotes stripped", gen.read_env(KEYS) == "quoted", gen.read_env(KEYS))
check("value keeps its own '='", gen.read_env("OTHER") == "a=b", gen.read_env("OTHER"))
kf.write_text("%s=http://127.0.0.1:20171\n" % KEYS, encoding="utf-8")
check("URL value kept whole", gen.read_env(KEYS) == "http://127.0.0.1:20171", gen.read_env(KEYS))
os.environ["IMAGE_GENERATION_KEYS_FILE"] = str(TMP / "does-not-exist.env")
check("missing keys file -> empty", gen.read_env(KEYS) == "", gen.read_env(KEYS))

print("--- _profile_frontmatter ---")
clean_env()
prof = TMP / ".image-generation" / "profile.md"
prof.write_text('---\nproxy: "http://127.0.0.1:20171"\ndefault_provider: heyroute\n---\nbody\n',
                encoding="utf-8")
fm = gen._profile_frontmatter()
check("value with ':' kept whole", fm.get("proxy") == "http://127.0.0.1:20171", fm.get("proxy"))
check("plain scalar parsed", fm.get("default_provider") == "heyroute", fm.get("default_provider"))
prof.write_text("no frontmatter here\n", encoding="utf-8")
check("no frontmatter -> {}", gen._profile_frontmatter() == {}, gen._profile_frontmatter())
prof.write_text("---\nproxy: x\n", encoding="utf-8")
check("unclosed frontmatter -> {}", gen._profile_frontmatter() == {}, gen._profile_frontmatter())
prof.unlink()
check("missing profile -> {}", gen._profile_frontmatter() == {}, gen._profile_frontmatter())

print("--- IMAGE_GENERATION_PROFILE override ---")
alt = TMP / "alt-profile.md"
alt.write_text("---\nproxy: http://alt:9\n---\n", encoding="utf-8")
os.environ["IMAGE_GENERATION_PROFILE"] = str(alt)
check("profile path overridden by env", gen._profile_frontmatter().get("proxy") == "http://alt:9",
      gen._profile_frontmatter())

print("--- resolve_proxy precedence (cli > env > profile > None) ---")
clean_env()
prof.write_text("---\nproxy: http://prof:1\n---\n", encoding="utf-8")
check("profile only", gen.resolve_proxy() == "http://prof:1", gen.resolve_proxy())
check("source = profile", gen.proxy_source() == "profile", gen.proxy_source())
os.environ["IMAGE_GENERATION_PROXY"] = "http://env:2"
check("env beats profile", gen.resolve_proxy() == "http://env:2", gen.resolve_proxy())
check("source = env", gen.proxy_source() == "env", gen.proxy_source())
check("cli beats env", gen.resolve_proxy("http://cli:3") == "http://cli:3", gen.resolve_proxy("http://cli:3"))
check("source = cli", gen.proxy_source("http://cli:3") == "cli", gen.proxy_source("http://cli:3"))
clean_env()
prof.unlink()
check("nothing set -> None", gen.resolve_proxy() is None, gen.resolve_proxy())
check("source None when unset", gen.proxy_source() is None, gen.proxy_source())

print("--- mask_proxy (credential hide) ---")
check("userinfo masked", gen.mask_proxy("http://u:p@127.0.0.1:20171") == "http://***:***@127.0.0.1:20171",
      gen.mask_proxy("http://u:p@127.0.0.1:20171"))
check("no userinfo untouched", gen.mask_proxy("http://127.0.0.1:20171") == "http://127.0.0.1:20171",
      gen.mask_proxy("http://127.0.0.1:20171"))
check("empty stays empty", gen.mask_proxy("") == "", gen.mask_proxy(""))

print("--- BOM tolerance (utf-8-sig) ---")
clean_env()
(TMP / ".image-generation" / "keys.env").write_text("%s=bomval\n" % KEYS, encoding="utf-8-sig")
check("BOM keys file read", gen.read_env(KEYS) == "bomval", gen.read_env(KEYS))
(TMP / ".image-generation" / "profile.md").write_text("---\nproxy: http://bom:1\n---\n", encoding="utf-8-sig")
check("BOM profile parsed", gen._profile_frontmatter().get("proxy") == "http://bom:1",
      gen._profile_frontmatter())

restore()
print("fails =", len(fails), fails)
sys.exit(1 if fails else 0)
