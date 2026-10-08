#!/usr/bin/env python3
"""Generate images via multi-provider image APIs (heyroute SSE / OpenAI-compatible JSON)."""
import argparse
import base64
import json
import mimetypes
import os
import re
import struct
import sys
import time
from pathlib import Path

import requests

PROVIDERS = {
    "infistar": {
        "base": "https://infistar.cc/v1",
        "env_key": "INFISTAR_API_KEY",
        "generations_path": "/images/generations",
        "edits_path": "/images/edits",
        "edit_format": "multipart",
        "response": "json",  # OpenAI sync JSON (NOT SSE like heyroute)
        "default_model": "gpt-image-2",
        "default_quality": "high",
        "n_max": 1,
        "size_rules": "pixel_window",  # success value 3520x2336 satisfies this window; see providers/infistar.md
        "common_sizes": ["1024x1024", "1536x1024", "1024x1536", "3520x2336"],
        "doc": "references/providers/infistar.md",
        # Per-model overrides: a model family on the same gateway can differ in
        # size contract, quality support, ref-passing format and extra params.
        "models": {
            # Volcengine Seedream rejects `quality` (422), defaults watermark=true
            # (adds an "AI-generated" mark) and takes refs as base64 in the JSON `images`
            # array instead of multipart edits.
            "doubao-seedream-5-0-260128": {
                "edit_format": "json_images",
                "default_quality": None,
                "extra_params": {"watermark": False, "output_format": "png"},
                "size_rules": "seedream_px",
                "common_sizes": ["2048x2048", "2560x1440", "3024x1296", "3840x2160", "4096x4096"],
            },
        },
    },
    "heyroute": {
        "base": "https://heyroute.ai/v1",
        "env_key": "HEYROUTE_API_KEY",
        "generations_path": "/images/generations",
        "edits_path": "/images/edits",
        "edit_format": "multipart_repeated_image",  # same field name repeated per official skill
        "response": "sse",  # started -> heartbeat* -> completed|error -> done
        "default_model": "gpt-image-2",
        "default_quality": "high",
        "n_max": 1,
        "size_rules": "pixel_window",
        # Official common sizes (heyroute-image-gen skill) - used for nearest-size suggestions.
        "common_sizes": ["1024x1024", "2048x2048", "2880x2880",
                         "1536x1024", "1024x1536", "3840x2160"],
        "preflight_path": "/models",
        "doc": "references/providers/heyroute.md",
    },
    "apiyi": {
        # APIYi acts as the BytePlus/Volcengine Seedream gateway. References are
        # NOT multipart: they ride in a top-level `image` array (base64 data URI),
        # and the Volcengine model rejects `quality` outright.
        "base": "https://api.apiyi.com/v1",
        "env_key": "APIYI_API_KEY",
        "generations_path": "/images/generations",
        "edit_format": "json_images",
        "ref_field": "image",
        "response": "json",
        "default_model": "seedream-5-0-260128",
        "default_quality": None,
        "n_max": 1,
        "max_refs": 10,
        # 6MB is the docs' recommended ceiling (timeout avoidance), 20MB the
        # documented hard failure zone (upstream 600s request-body timeout).
        "warn_ref_bytes": 6 * 1024 * 1024,
        "max_ref_bytes": 20 * 1024 * 1024,
        "size_rules": "seedream_lite_px",
        "common_sizes": ["2048x2048", "3072x3072", "4096x2304", "3744x2496", "2560x1440"],
        "extra_params": {
            "watermark": False,
            "output_format": "png",
            "sequential_image_generation": "disabled",
        },
        # Families on this gateway differ in which params they accept: pro/flash
        # 400 on `sequential_image_generation` (even "disabled"), and 4.5/4.0 are
        # jpeg-only (no `output_format`). Overrides replace extra_params wholesale.
        "models": {
            "seedream-5-0-pro-260628": {"extra_params": {"watermark": False, "output_format": "png"}},
            "seedream-5-0-flash-260915": {"extra_params": {"watermark": False, "output_format": "png"}},
            "seedream-4-5-251128": {"extra_params": {"watermark": False}},
            "seedream-4-0-250828": {"extra_params": {"watermark": False}},
        },
        "preflight_path": "/models",
        "doc": "references/providers/apiyi.md",
    },
    "volcengine": {
        # Volcengine Ark (ByteDance): official OpenAI-compatible image endpoint.
        # References ride in a top-level `image` array (base64 data URI). Ark's
        # `quality` is a RESOLUTION tier (1K/1.5K/2K), not low/medium/high, so we
        # never send it and pass exact pixel sizes instead.
        "base": "https://ark.cn-beijing.volces.com/api/v3",
        "env_key": "ARK_API_KEY",
        "generations_path": "/images/generations",
        "edit_format": "json_images",
        "ref_field": "image",
        "response": "json",
        "default_model": "doubao-seedream-5-0-pro-260628",
        "default_quality": None,
        "n_max": 1,
        "max_refs": 10,
        "size_rules": "seedream_pro_px",
        "common_sizes": ["2048x2048", "2496x1664", "2816x1584", "3136x1344", "2048x1152", "1024x1024"],
        "extra_params": {"watermark": False, "response_format": "url"},
        "preflight_path": "/models",
        "doc": "references/providers/volcengine.md",
    },
}

SIZE_RULES = {
    # edge_multiple is NOT a validation rule: providers are not checked against
    # it, so an odd edge (e.g. infistar's measured 1672x941) goes through and the
    # API decides. It survives only as the tier-conversion step so tiered specs
    # ("3:2 1K") still land on tidy sizes.
    "pixel_window": {
        "edge_multiple": 16,
        "max_edge": 3840,
        "max_ratio": 3.0,
        "min_px": 655360,
        "max_px": 8294400,
        "tier_base": 1024,
    },
    # Volcengine doubao-seedream: explicit WIDTHxHEIGHT, total px in
    # [2560x1440, 4096x4096], aspect ratio in [1/16, 16]; no edge-multiple rule.
    # (Or a `2k`/`3k`/`4k` keyword, which lets the model pick exact pixels.)
    "seedream_px": {
        "edge_multiple": None,
        "max_edge": 4096,
        "max_ratio": 16.0,
        "min_px": 2560 * 1440,
        "max_px": 4096 * 4096,
        "tier_base": 1024,
    },
    # BytePlus Seedream 5.0-lite (seedream-5-0-260128): explicit WxH, total px
    # in [2560x1440, ~10.4MP], aspect ratio in [1/16, 16], no edge-multiple rule.
    # Ceiling follows the Volcengine 3K tier (3072x3072 x 1.1025); APIYi's own
    # model-agnostic range is looser, so this stays the conservative bound.
    "seedream_lite_px": {
        "edge_multiple": None,
        "max_edge": 4096,
        "max_ratio": 16.0,
        "min_px": 2560 * 1440,
        "max_px": 10404496,
        "tier_base": 1024,
    },
    # Volcengine Ark Seedream 5.0 Pro: explicit WxH, total px in
    # [921600, 4624220], aspect ratio in [1/16, 16], every edge > 14; no
    # edge-multiple rule. Pro caps at 2K (no 4K tier).
    "seedream_pro_px": {
        "edge_multiple": None,
        "max_edge": 8192,
        "max_ratio": 16.0,
        "min_px": 921600,
        "max_px": 4624220,
        "tier_base": 1024,
    },
}

ALLOWED_QUALITIES = ("low", "medium", "high", "auto")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


_RESULT_PATH = None


def configure_stdio():
    """Choose a stdio encoding from the environment, changing nothing outside.

    A piped stream has no way to ask its consumer which charset it expects,
    so the environment has to declare the answer:
      - PYTHONIOENCODING / PYTHONUTF8 set -> honoured as given;
      - interactive console               -> left untouched (a Windows console
        is written through WriteConsoleW, which already renders Unicode, and
        a Unix console is the locale, normally UTF-8);
      - otherwise                         -> UTF-8, the one encoding that
        Unix pipes, macOS, modern PowerShell and MCP tooling agree on.
    The host locale default is deliberately not inherited: it is this
    machine's own preference, not the consumer's contract.
    No registry key, code page, locale, profile or shell setting is touched.
    Stream by stream: stdout and stderr can be redirected independently.
    """
    if os.environ.get("PYTHONIOENCODING") or os.environ.get("PYTHONUTF8"):
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                continue
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def write_result(payload):
    """Persist the run outcome as UTF-8 JSON beside the output image.

    Two jobs at once:
      * an archive record - the exact API response, request id and paths
        survive even if the host shell mangles the console copy;
      * a draft generation-parameter file - rename it and add an asset id /
        timestamp to catalogue the run, instead of transcribing by hand.

    Returns the path written, or None.
    """
    if _RESULT_PATH is None:
        return None
    try:
        _RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RESULT_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return _RESULT_PATH
    except OSError:
        return None


def die(msg, code=1):
    write_result({"status": "error", "error": msg})
    print(msg, file=sys.stderr)
    sys.exit(code)


def _read_keys_file(name):
    """Read one K=V key from an optional plain-text keys file.

    Lets a harness with no env-delivery mechanism pick up keys by copying one
    file. Path is $IMAGE_GENERATION_KEYS_FILE, defaulting to
    .image-generation/keys.env (relative to the working directory). Lines are
    plain `NAME=VALUE` - an `export ` prefix is NOT stripped - and `#` starts a
    comment. Values are never echoed. A UTF-8 BOM is tolerated.
    """
    path = os.environ.get("IMAGE_GENERATION_KEYS_FILE") or str(
        Path(".image-generation") / "keys.env")
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, val = line.partition("=")
        if k.strip() == name:
            return val.strip().strip('"').strip("'")
    return ""


def read_env(name):
    """Read an env var: process env -> Windows User registry -> optional keys file.

    User-scope registry variables are not inherited by already-running hosts, so
    the registry fallback makes keys persisted via
    [Environment]::SetEnvironmentVariable usable in any new shell. The keys file
    is the last resort for harnesses that deliver neither.
    """
    v = os.environ.get(name)
    if v:
        return v.strip()
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                val, _ = winreg.QueryValueEx(key, name)
                if val:
                    return val.strip()
        except OSError:
            pass
    return _read_keys_file(name)


def _profile_path():
    """Path to the project profile: $IMAGE_GENERATION_PROFILE or the default."""
    return Path(os.environ.get("IMAGE_GENERATION_PROFILE")
                or (Path(".image-generation") / "profile.md"))


def _profile_frontmatter():
    """Parse the profile's leading YAML frontmatter into a {key: value} dict.

    Deliberately tiny (no YAML dependency): only top-level `key: value` lines in
    the leading `--- ... ---` block, quotes stripped. Returns {} if absent.
    """
    try:
        text = _profile_path().read_text(encoding="utf-8-sig").lstrip("\ufeff")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)
    if len(block) < 3:
        return {}
    out = {}
    for line in block[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_proxy(cli_value=None):
    """Outbound proxy URL: --proxy > $IMAGE_GENERATION_PROXY > profile `proxy:`.

    Needed when a harness routes egress through a sandbox proxy that connects
    directly (a blocked image-CDN domain is then unreachable without the user's
    own proxy, and fails as a bare timeout). Setting it also bypasses the
    sandbox's network policy/logging - a user-side tradeoff.
    """
    if cli_value:
        return cli_value.strip()
    env = os.environ.get("IMAGE_GENERATION_PROXY")
    if env:
        return env.strip()
    return _profile_frontmatter().get("proxy") or None


def proxy_source(cli_value=None):
    """Which source supplied the proxy: 'cli' | 'env' | 'profile' | None."""
    if cli_value:
        return "cli"
    if os.environ.get("IMAGE_GENERATION_PROXY"):
        return "env"
    if _profile_frontmatter().get("proxy"):
        return "profile"
    return None


def mask_proxy(url):
    """Hide userinfo credentials in a proxy URL for display.

    Keeps scheme/host/port (useful for debugging) but replaces any `user:pass@`
    with `***:***@`, so credentials never reach the terminal, redirected logs,
    or a host's command logs.
    """
    if not url:
        return url
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*://)(?:[^@/]+@)(.+)$", url)
    return m.group(1) + "***:***@" + m.group(2) if m else url


def resolve_provider(name, model=None):
    """Return (config, model): the gateway config merged with the selected
    model's overrides (families on one gateway differ in size rules, quality
    support, ref-passing format and extra params)."""
    base = PROVIDERS.get(name)
    if not base:
        die(f"unknown provider {name!r}; known: {', '.join(PROVIDERS)}")
    model = model or base["default_model"]
    overrides = (base.get("models") or {}).get(model) or {}
    return {**base, **overrides}, model


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _explicit_errors(w, h, rule):
    errors = []
    if max(w, h) > rule["max_edge"]:
        errors.append(f"longest edge must be <= {rule['max_edge']} (got {max(w, h)})")
    if w / h > rule["max_ratio"] or h / w > rule["max_ratio"]:
        errors.append(f"aspect ratio must be at most {rule['max_ratio']}:1 (got {w}:{h})")
    px = w * h
    if px < rule["min_px"] or px > rule["max_px"]:
        errors.append(f"total pixels {px} outside [{rule['min_px']}, {rule['max_px']}]")
    return errors


def _size_ok(w, h, rule):
    """Single source of truth for the size contract: the rules live in
    _explicit_errors and nothing else may restate them."""
    return not _explicit_errors(w, h, rule)


def _nearest_edge(v, multiple):
    """Round down to the rule's edge multiple (e.g. 16)."""
    m = multiple or 1
    return max(m, int(v) // m * m)


def _suggest_sizes(w, h, rule, common_sizes):
    """Nearest legal sizes: (1) keep aspect ratio, fit limits; (2) closest common sizes."""
    out = []
    ratio = w / h
    scale = 1.0
    if max(w, h) > rule["max_edge"]:
        scale = min(scale, rule["max_edge"] / max(w, h))
    px = w * h
    if px > rule["max_px"]:
        scale = min(scale, (rule["max_px"] / px) ** 0.5)
    elif px < rule["min_px"]:
        scale = max(scale, (rule["min_px"] / px) ** 0.5)
    if abs(scale - 1.0) > 1e-9:
        mult = rule["edge_multiple"] or 1
        nw, nh = _nearest_edge(w * scale, mult), _nearest_edge(h * scale, mult)
        while nw > mult and nh > mult and not _size_ok(nw, nh, rule):
            nw -= mult
            nh -= mult
        if _size_ok(nw, nh, rule):
            out.append(f"keep ratio ~{ratio:.2f}: {nw}x{nh}")
    ranked = sorted(
        (s for s in (common_sizes or [])),
        key=lambda s: abs(int(s.split("x")[0]) * int(s.split("x")[1]) - w * h),
    )
    seen = set(out)
    for s in ranked:
        cw, ch = (int(x) for x in s.split("x"))
        if s in seen or not _size_ok(cw, ch, rule):
            continue
        out.append(f"official common size: {s}")
        seen.add(s)
        if len(out) >= 3:
            break
    return out


def check_size_or_die(w, h, provider):
    """Strict validation: never auto-repair. Report violation + nearest candidates, then exit."""
    rule = SIZE_RULES[provider["size_rules"]]
    errs = _explicit_errors(w, h, rule)
    if not errs:
        return
    lines = [f"size {w}x{h} is INVALID for provider {provider.get('doc', '')}:"]
    lines += [f"  - {e}" for e in errs]
    sug = _suggest_sizes(w, h, rule, provider.get("common_sizes"))
    if sug:
        lines.append("nearest legal sizes (pick one, then re-confirm with the user):")
        lines += [f"  * {s}" for s in sug]
    lines.append("refusing to auto-substitute a size; no request was sent.")
    die("\n".join(lines))


def resolve_size(spec, provider):
    """Resolve size spec -> (w, h, note).

    Accepts: "1536x1024" | tiered "3:2 1K" | "4K 3:2".
    "auto" is rejected with a dedicated error (user rule: explicit pixels only).
    Tiered: short edge target = tier_base * K, exact ratio, edge-multiple edges,
    clamped down to the provider's legal maximum.
    """
    spec = spec.strip()
    rule = SIZE_RULES[provider["size_rules"]]

    # User rule: explicit pixels only. auto -> 1:1 square (measured), hard-forbidden.
    if spec.lower() == "auto":
        die("size 'auto' is forbidden: give an explicit WIDTHxHEIGHT (e.g. 1792x1008)")

    m = re.fullmatch(r"(\d+)\s*[xX]\s*(\d+)", spec)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if w <= 0 or h <= 0:
            die(f"invalid size {spec!r}: both edges must be >= 1")
        return w, h, None

    m = re.fullmatch(
        r"(?:(\d+)\s*:\s*(\d+)\s*(\d+)\s*[kK]|(\d+)\s*[kK]\s*(\d+)\s*:\s*(\d+))",
        spec.replace(",", " ").strip(),
    )
    if not m:
        die(
            f"invalid size spec: {spec!r}\n"
            "expected WIDTHxHEIGHT or tiered form like '3:2 1K' / '4K 3:2'"
        )
    if m.group(1):
        rw, rh, k = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        k, rw, rh = int(m.group(4)), int(m.group(5)), int(m.group(6))
    if k < 1 or rw < 1 or rh < 1:
        die(f"invalid tiered spec {spec!r}: ratio and K must be positive")

    g = _gcd(rw, rh)
    aw, ah = rw // g, rh // g
    mult = rule["edge_multiple"] or 1
    t_opt = max(1, round(rule["tier_base"] * k / (mult * min(aw, ah))))
    t = t_opt
    while t >= 1:
        w, h = mult * t * aw, mult * t * ah
        if _size_ok(w, h, rule):
            break
        t -= 1
    else:
        w, h = mult * t_opt * aw, mult * t_opt * ah
        lines = [f"no legal size for ratio {rw}:{rh} at {k}K ({w}x{h}) under provider limits:"]
        lines += [f"  - {e}" for e in _explicit_errors(w, h, rule)]
        sug = _suggest_sizes(w, h, rule, provider.get("common_sizes"))
        if sug:
            lines.append("nearest legal sizes (pick one, then re-confirm with the user):")
            lines += [f"  * {s}" for s in sug]
        die("\n".join(lines))

    note = f"{rw}:{rh} {k}K -> {w}x{h}"
    if t < t_opt:
        note += " (clamped down to provider limits)"
    return w, h, note


def image_size_bytes(data):
    """Read (w, h) from a PNG or JPEG header; None if unrecognized.

    Providers differ on output format (seedream returns JPEG even when asked for
    PNG), so resolution verification must not assume PNG.
    """
    if len(data) >= 24 and data[:8] == PNG_MAGIC and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":  # JPEG: walk segments to the SOFn frame header
        i, n = 2, len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker == 0xFF:  # fill byte before a marker
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg_len
    return None


def image_size(path):
    return image_size_bytes(Path(path).read_bytes())


def detect_format(data):
    """'png' | 'jpg' | None, from the magic bytes alone."""
    if data[:8] == PNG_MAGIC:
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    return None


def write_output(raw, out, jpeg_quality):
    """Persist the provider's bytes under the format --out asks for.

    .png asks for PNG; every other extension (including none) means JPEG, which
    is the library default. Bytes already in the requested format are written
    untouched - re-encoding a JPEG to JPEG would cost quality for nothing. A
    source carrying alpha cannot become JPEG, so it falls back to PNG beside the
    request and reports it rather than silently dropping transparency.

    Returns (path actually written, warning or None).
    """
    src = detect_format(raw) or "png"
    wants_png = out.suffix.lower() == ".png"

    if wants_png:
        out.write_bytes(raw)
        return out, (f"note: source is {src.upper()} but --out asked for PNG; wrote the original bytes"
                     if src != "png" else None)

    if src != "jpg":
        try:
            from PIL import Image, ImageOps
            import io as _io
        except ImportError:
            die("Pillow is required to write JPEG output; install pillow or pass --out *.png")
        try:
            im = Image.open(_io.BytesIO(raw))
            im.load()  # truncated payloads only fail here, not on open()
        except Exception as exc:
            die(
                f"provider returned something that is not a usable image ({type(exc).__name__}).\n"
                f"  First bytes: {raw[:24]!r}\n"
                f"  Nothing was written to {out.name}; check the console for that request."
            )
        with im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                png_out = out.with_suffix(".png")
                im.convert("RGBA").save(png_out, "PNG")
                return png_out, (
                    f"note: source carries alpha, which JPEG cannot keep -> wrote {png_out.name} "
                    f"instead of {out.name}; ask for .png explicitly to silence this"
                )
            rgb = im.convert("RGB")
    else:
        rgb = None

    target = out if out.suffix else out.with_name(out.name + ".jpg")
    if rgb is None:
        target.write_bytes(raw)
        return target, None
    rgb.save(target, "JPEG", quality=jpeg_quality, optimize=True, subsampling=0)
    return target, None


def sse_events(resp):
    """Yield (event, data) pairs from an SSE byte stream.

    Decode as UTF-8 ourselves: requests' decode_unicode=True falls back to
    ISO-8859-1 when the response carries no charset, which turns any non-ASCII
    upstream error message into mojibake (and the mojibake is what the operator
    ends up reading). Read bytes and decode explicitly instead.
    """
    event, data_lines = None, []
    for raw in resp.iter_lines(decode_unicode=False, chunk_size=None):
        if raw is None:
            continue
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if event is not None or data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
        elif line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if event is not None or data_lines:
        yield event, "\n".join(data_lines)


def extract_image(data):
    """Return b64/url from a completed payload (SSE data or plain JSON)."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("data")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0].get("b64_json") or items[0].get("url")
    return payload.get("b64_json") or payload.get("url")


def read_image_token(resp, cap_s=240):
    """Return image token from either SSE stream (heyroute) or plain JSON (OpenAI-compatible).

    Branch on Content-Type: touching resp.text on an SSE response would buffer the
    entire stream before parsing, defeating the incremental heartbeat/cap checks.
    """
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "event-stream" not in ctype:
        text = resp.text or ""
        token = extract_image(text)
        if token:
            return token
        hint = " (body looks like SSE; check Content-Type)" if text.lstrip().startswith(("event:", "data:")) else ""
        die("response is neither a JSON image payload nor parseable:" + hint + "\n" + text[:600])

    t0 = time.monotonic()
    completed_data = None
    for event, data in sse_events(resp):
        if time.monotonic() - t0 > cap_s:
            die(f"stream exceeded {cap_s}s total - stalled connection or abnormally slow; aborting (verify console if unsure)")
        if event == "error":
            try:
                message = json.loads(data)["error"]["message"]
            except Exception:
                message = data
            die(f"generation failed (charge refunded): {message}")
        elif event == "completed":
            completed_data = data
        elif event == "done":
            break
        # OpenAI-style SSE: bare `data:` frames, no event names. Accept any frame
        # that already carries an image payload (heyroute heartbeats carry none,
        # so this is safe for both dialects).
        if event is None or event in ("message", "response"):
            token = extract_image(data)
            if token:
                return token
    if completed_data:
        token = extract_image(completed_data)
        if token:
            return token
    die("stream ended without a completed image payload")


def preflight(base, api_key, provider, proxies=None):
    """Cheap connectivity check (GET /models, no charge) so connection problems
    surface in seconds instead of stalling a billable POST."""
    path = provider.get("preflight_path")
    if not path:
        return
    try:
        requests.get(base + path,
                     headers={"Authorization": f"Bearer {api_key}"},
                     timeout=(8, 15), proxies=proxies)
    except requests.RequestException as exc:
        die(f"preflight connection failed (nothing was billed): {exc}")


def _form_val(v):
    """Multipart form fields are strings; render booleans as lowercase."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def _data_uri(path):
    """Base64 data URI for providers that take references in the JSON body."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def main():
    global _RESULT_PATH
    configure_stdio()
    ap = argparse.ArgumentParser(description="Generate images via multi-provider image APIs")
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--model", default=None, help="defaults to provider default_model")
    ap.add_argument("--size", required=True,
                    help="WIDTHxHEIGHT or tiered like '16:9 1K' / '4K 3:2' (auto is forbidden)")
    ap.add_argument("--quality", default=None, choices=ALLOWED_QUALITIES,
                    help="defaults to provider default_quality (high)")
    ap.add_argument("--n", type=int, default=1, help="provider n_max may be 1")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="prompt text")
    src.add_argument("--prompt-file", help="path to UTF-8 prompt text file")
    ap.add_argument("--image", action="append", default=[],
                    help="reference image path (repeatable; first = subject, rest = references)")
    ap.add_argument("--mask", default=None,
                    help="optional PNG mask for edits (transparent = area to repaint)")
    ap.add_argument("--out", required=True,
                    help="output image path; format follows the extension: .png keeps PNG, "
                         "anything else (or none) is written as JPEG")
    ap.add_argument("--api-base", default=None, help="override provider base URL")
    ap.add_argument("--proxy", default=None,
                    help="HTTP(S) proxy URL for outbound requests; falls back to "
                         "$IMAGE_GENERATION_PROXY then the profile 'proxy:' field")
    ap.add_argument("--timeout", type=int, default=240,
                    help="SSE stream total cap AND sync-JSON first-byte window seconds (30~120s typical)")
    ap.add_argument("--jpeg-quality", type=int, default=95,
                    help="JPEG quality when --out is not .png (default 95)")
    args = ap.parse_args()

    if not 1 <= args.jpeg_quality <= 95:
        die(f"--jpeg-quality must be in 1..95 (got {args.jpeg_quality})")

    # The sidecar sits next to its image with only the extension swapped, so
    # cataloguing is a rename, not a hand-written file.
    _RESULT_PATH = Path(args.out).with_suffix(".json")

    provider, model = resolve_provider(args.provider, args.model)
    quality = args.quality or provider.get("default_quality", "high")
    n_max = provider.get("n_max")
    if n_max and args.n > n_max:
        die(f"provider {args.provider} only supports n <= {n_max}")

    proxy = resolve_proxy(args.proxy)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    if proxy:
        print(f"proxy: {mask_proxy(proxy)} (from {proxy_source(args.proxy)})", file=sys.stderr)

    api_key = read_env(provider["env_key"])
    if not api_key:
        die(f"{provider['env_key']} is not set (process env, keys file, or Windows User env)")

    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            die(f"prompt file not readable: {exc}")
    else:
        prompt = (args.prompt or "").strip()
    if not prompt:
        die("prompt is empty")

    w, h, note = resolve_size(args.size, provider)
    if note:
        print(f"size resolved: {note}", file=sys.stderr)
    size_str = f"{w}x{h}"
    check_size_or_die(w, h, provider)

    # Validate every local input BEFORE any network call: the probes below are
    # free but still requests, and a typo'd path should never cost one.
    json_images = bool(args.image) and provider.get("edit_format") == "json_images"
    if args.image:
        for p in args.image:
            if not Path(p).exists():
                die(f"image not found: {p}")
        max_refs = provider.get("max_refs")
        if max_refs and len(args.image) > max_refs:
            die(f"{args.provider} accepts at most {max_refs} reference images (got {len(args.image)})")
    if args.mask and json_images:
        die(f"--mask is not supported for {args.provider}/{model} (references go via the JSON body)")
    if args.mask and not Path(args.mask).exists():
        die(f"mask not found: {args.mask}")

    base = (args.api_base or provider["base"]).rstrip("/")
    # Protocol-faithful headers: SSE accept + stream flag only for SSE providers
    # (OpenAI images has no `stream` param; sending it can force SSE dialects).
    is_sse = provider.get("response") == "sse"
    headers = {"Authorization": f"Bearer {api_key}"}
    if is_sse:
        headers["Accept"] = "text/event-stream"

    # Layer 1: cheap connectivity probe before any billable POST.
    preflight(base, api_key, provider, proxies)

    # Layer 2: connect fails fast (8s). Read timeout depends on protocol:
    #  - SSE providers: heartbeat every 15s keeps the socket alive -> 60s silence = dead.
    #  - sync-JSON providers (OpenAI): no heartbeat, first byte arrives only when the
    #    whole generation finishes -> read window must cover the full generation cap.
    if is_sse:
        net_timeout = (8, 60)
    else:
        net_timeout = (8, args.timeout)

    # stream flag: SSE providers only (protocol declaration per heyroute official skill)
    use_stream = is_sse

    # Fields both branches share, built once so the two request shapes cannot drift.
    common = {"model": model, "prompt": prompt, "size": size_str}
    if quality:
        common["quality"] = quality

    try:
        if args.image and not json_images:
            url = base + provider["edits_path"]
            data = {**common, "n": "1"}  # multipart fields are strings
            for k, v in (provider.get("extra_params") or {}).items():
                data[k] = _form_val(v)
            if use_stream:
                data["stream"] = "true"
            files = []
            for p in args.image:
                path = Path(p)
                mime = mimetypes.guess_type(path.name)[0] or (
                    "image/png" if path.suffix.lower() == ".png" else "application/octet-stream")
                files.append(("image", (path.name, path.read_bytes(), mime)))
            if args.mask:
                mpath = Path(args.mask)
                files.append(("mask", (mpath.name, mpath.read_bytes(), "image/png")))
            resp = requests.post(url, headers=headers, data=data, files=files,
                                 timeout=net_timeout, stream=True, proxies=proxies)
        else:
            url = base + provider["generations_path"]
            body = {**common, "n": 1}
            body.update(provider.get("extra_params") or {})
            if json_images:
                refs = [_data_uri(Path(p)) for p in args.image]
                total = sum(len(r) for r in refs)
                warn_bytes = provider.get("warn_ref_bytes")
                if warn_bytes and total > warn_bytes:
                    print(
                        f"WARNING: reference images total {total} base64 chars, above the recommended "
                        f"{warn_bytes} for {args.provider}; the cross-border upload may time out",
                        file=sys.stderr,
                    )
                max_ref_bytes = provider.get("max_ref_bytes")
                if max_ref_bytes and total > max_ref_bytes:
                    die(
                        f"reference images total {total} base64 chars, over the hard {max_ref_bytes} limit "
                        f"for {args.provider} (upstream request-body timeout); re-encode them smaller"
                    )
                body[provider.get("ref_field", "images")] = refs
            if use_stream:
                body["stream"] = True
            resp = requests.post(url, headers=headers, json=body,
                                 timeout=net_timeout, stream=True, proxies=proxies)
    except requests.exceptions.ConnectTimeout:
        die(f"connect timed out ({net_timeout[0]}s) - network unreachable, nothing was sent")
    except requests.exceptions.ReadTimeout:
        die(
            f"read timed out after {net_timeout[1]}s waiting for the first response byte.\n"
            f"The server may STILL BE GENERATING - a successful job after client abort\n"
            f"may still be billed. Check the provider console before retrying."
        )
    except requests.exceptions.RequestException as exc:
        die(f"request failed: {exc}")

    if resp.status_code >= 400:
        # Decode the body as UTF-8 explicitly: resp.text honours a charset header
        # but silently falls back to ISO-8859-1 without one, which mojibakes any
        # non-ASCII provider error.
        try:
            message = json.loads(resp.content.decode("utf-8", errors="replace"))["error"]["message"]
        except Exception:
            message = resp.content.decode("utf-8", errors="replace")[:600]
        die(f"HTTP {resp.status_code}: {message}")

    # Layer 3: total stream cap inside read_image_token (SSE) / full window (JSON).
    token = read_image_token(resp, cap_s=args.timeout)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if token.startswith("http://") or token.startswith("https://"):
        # A transient failure here is a KNOWN issue on some channels (e.g. Volcengine
        # TOS over a proxy): the generation already succeeded and is billed, so the
        # message must warn against simply re-running the order.
        try:
            dl = requests.get(token, timeout=args.timeout, proxies=proxies)
            dl.raise_for_status()
        except requests.RequestException as exc:
            die(
                f"image download failed: {exc}\n"
                f"  The generation itself SUCCEEDED and may already be billed - do NOT just re-run it.\n"
                f"  Retry downloading the returned asset instead (the link expires):\n"
                f'    curl.exe -L -o "{args.out}" "{token}"'
            )
        raw = dl.content
    else:
        raw = base64.b64decode(token)

    # Delivery format follows --out: .png asks for PNG explicitly, everything else
    # (including a missing/unknown extension) becomes JPEG at --jpeg-quality.
    # Providers are inconsistent about the bytes they return, so the request's
    # extension is the only reliable statement of intent.
    wrote, note = write_output(raw, out, args.jpeg_quality)
    if note:
        print(note, file=sys.stderr)

    actual = image_size(wrote)
    actual_str = f"{actual[0]}x{actual[1]}" if actual else "unknown"
    mismatch = bool(actual) and actual_str != size_str

    # Console report: everything about THIS RUN (paths, mismatch flags).
    report = {
        "saved": str(wrote),
        "provider": args.provider,
        "model": model,
        "quality": quality,
        "endpoint": "edits" if (args.image and not json_images) else "generations",
        "requested_spec": args.size,
        "resolved_size": size_str,
        "actual_size": actual_str,
        "size_mismatch": mismatch,
        "skill_update_suggested": mismatch,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Sidecar: a draft generation-parameter file. It holds only cataloguing
    # fields - no run-time bookkeeping. Cataloguing is then a rename plus an
    # `asset` id / timestamp.
    sidecar = {
        "provider": args.provider,
        "model": model,
        "endpoint": report["endpoint"],
        "requested_spec": args.size,
        "resolved_size": size_str,
        "actual_size": actual_str,
        "quality": quality,
        "n": args.n,
        "watermark": (provider.get("extra_params") or {}).get("watermark"),
        "reference_images": [str(Path(p)) for p in args.image],
        "mask": str(Path(args.mask)) if args.mask else None,
        "prompt": prompt,
    }
    written_sidecar = write_result(sidecar)
    if written_sidecar:
        print(f"sidecar: {written_sidecar}  (rename to <asset>.json when cataloguing)", file=sys.stderr)

    if mismatch:
        print(
            f"WARNING: actual resolution {actual_str} != requested {size_str}.\n"
            f"REPORT to the user first and WAIT for their decision:\n"
            f"  - do NOT retry, do NOT edit the provider archive automatically;\n"
            f"  - record it in the provider archive 'Known issues' ONLY if the user\n"
            f"    confirms it is a deterministic (reproducible) problem.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
