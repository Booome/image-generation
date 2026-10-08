# Provider Profile · Infistar
**English** | [中文](infistar.zh-CN.md)

> Fixed sections for a single-provider profile: doc location / authentication & endpoint / parameter allowlist / model table / size rules / response format / billing / known issues / provider-specific parameters.
> Copy this structure when adding a provider; this profile was built manually (2026-09-23), sources = live API probes + user success cases. Latest live update: **2026-09-28** (`gpt-image-2.5-sunburst` image edit).

## Doc Location

- **No public skill/doc repo** (unlike heyroute) — behavior is governed by live API probes + user success parameters; record official doc URLs here if found.
- API self-description (with Bearer): `GET /v1/models` (198 models measured, including `gpt-image-2`)
- Probe (rejected at the validation layer = not billed): send an invalid `size` (e.g. `bogus-size`) → `400 {"message":"size must be auto or WIDTHxHEIGHT","type":"new_api_error"}` — **returns only the format, not the allowlist values**.
- Gateway type: **new-api** (`new_api_error`), fully OpenAI-protocol compatible.

## Authentication & Endpoint

- Authentication: `Authorization: Bearer $INFISTAR_API_KEY`
- Base: `https://infistar.cc/v1`
- `POST /v1/images/generations` — JSON, text-to-image
- `POST /v1/images/edits` — `multipart/form-data`, multiple images via repeated `image` fields. **Verified working** (2026-09-28, `gpt-image-2.5-sunburst`, 2 images; see "Provider-specific Parameters · Image Edit")

## Parameter Allowlist (OpenAI-compatible family, filled in as probes progress)

| Parameter | Values | Status |
|---|---|---|
| `model` | `gpt-image-2` (also `gpt-image-2.5-sunburst/flare`, qwen-image*, doubao-seedream*, wan2.7-image*, etc.) | Confirmed in /v1/models |
| `prompt` | text | required |
| `n` | upper limit unknown | use 1 conservatively |
| `size` | `auto` or `WIDTHxHEIGHT` (format measured); **allowlist values unknown** | ⚠️ TBD — governed by user success parameters, see below |
| `quality` | OpenAI convention `low/medium/high/auto` | `high` verified working (2026-09-28 edits order); other tiers untested |

### size Rules (`size_rules: pixel_window`)

- **Verified success (user case, 2026-09-23)**: `3520x2336` (= infinite canvas 4K 3:2 tier `imageSizePresets["4k"]["3:2"]`) → **native output 3520×2336, 8.22MP, exact, no crop and no scaling** (carrier image). **Native 4K holds on this channel**.
- This success value happens to satisfy the same pixel window as heyroute (≤3840 / ≤8.29MP) — for now reuse `pixel_window` for local validation (it does not block values users commonly use); **the multiple-of-16 rule is no longer a local validation item** (as of 2026-09-29 the side-length multiple check was removed for all providers); whether the allowlist is wider is unknown, the server's 400 is authoritative.
- Verified rejection: `bogus-size` (format error, 400, not billed).
- `auto`: **globally disabled in this skill** (explicit-pixel hard rule).
- Tier conversion reuses the colloquial format `3:2 1K/4K` (`3:2 4K` → clamps to the pixel_window ceiling 3504x2336 — **note: the channel's measured-usable value 3520x2336 is better than the clamped value**; when producing 4K 3:2, **write `3520x2336` explicitly**, do not use tier conversion).

## Model Table (measured 2026-09-23, image types excerpted)

`gpt-image-2`, `gpt-image-2.5-sunburst`, `gpt-image-2.5-flare` (all three tagged only `image-generation` in `supported_endpoint_types`); `step-image-edit-2` (**the only one tagged `image-edit`**); qwen-image family, doubao-seedream family, wan2.7 family, grok-imagine-image, gemini text family.

- ⚠️ **The `supported_endpoint_types` tag ≠ actual capability**: although `gpt-image-2.5-sunburst` is tagged only `image-generation`, its `/v1/images/edits` is **verified working** (2026-09-28). Do not conclude "cannot edit" from that field alone.

## Response Format (`response: json` — key difference from heyroute)

- **OpenAI standard synchronous JSON** (expected; the `stream` parameter is not sent by protocol): `{"data":[{"b64_json":...}]}` — **not SSE** (heyroute is the SSE one)
- **Measured note**: an early request carrying `stream: true` (not a standard OpenAI images parameter) made new-api return **SSE with bare `data:` frames (no `event:` name)** — `read_image_token` already handles both dialects (Content-Type auto-routing + bare data-frame parsing)
- `generate.py` already adapted: non-SSE responses go straight through the JSON parsing path

## Billing Rules

- A validation-layer 400 is not billed (measured with the size probe)
- The specific billing/refund policy is **unknown** (no public docs) — by the general principle: on failure, ask the user to check the console

## Known Issues

- The size allowlist is not public and the probe returns no values — **before the first order you must obtain user success parameters or a boundary probe confirmed by the user**
- ~~Whether `edits` + `gpt-image-2` supports a reference image (endpoint type is tagged only image-generation) — untested; fallback `step-image-edit-2`~~ **Closed loop (2026-09-28)**: `gpt-image-2.5-sunburst` via `/v1/images/edits` with multiple reference images **verified effective**, see "Provider-specific Parameters · Image Edit"; `gpt-image-2` itself still untested.
- **edits resolution deviation (deterministic, 2026-09-28)**: `size=1792x1008` (`16:9 1K` tier conversion value) → **actually produces `1672x941`** (about 1.57MP total). Same behavior as heyroute `gpt-image-2` — **size only takes the aspect ratio and produces output at a fixed pixel budget**; to get a higher resolution you must reverse-engineer the input from measured pixels, do not count on tier conversion.
- **Non-deterministic 400 seen on edits (2026-09-28)**: two Chinese-language `当前模型无法处理输入图像。请检查输入图片是否安全或者已下载，不适合进行图像编辑。` errors (with 3 images and 2 images respectively), followed by a **successful render with the same format and 2 images** — cause not identified. **Do not judge that the model does not support editing from a single 400**; retry once.

## Provider-specific Parameters

- **None** beyond the OpenAI standard set; below is the measured behavior of the gpt-image family `edits`.

### Image Edit (`POST /v1/images/edits`, measured 2026-09-28)

- **Works**: `--provider infistar --model gpt-image-2.5-sunburst` + `edit_format: multipart` (an existing `generate.py` path; ran through without code changes).
- **How images are passed**: multiple images via repeated `image` fields — the 1st = base image (preserves composition/pose), the 2nd = reference image (controls appearance); measured **2 images effective**.
- **Parameters**: `size=16:9 1K` → `1792x1008` (passes local `pixel_window` validation), `quality=high`, `n=1`, **no `stream` sent** (unlike heyroute's fixed SSE).
- **Effect verified**: the base image's composition and pose were preserved, and the reference image's appearance features were written in (the juvenile was switched back to the correct fur color / bone-spur design per the character design sheet) — **the reference image genuinely takes effect, it is not text-to-image only**.
- **Resolution deviation and non-deterministic 400 samples**: see "Known Issues" (not repeated here).

## Seedream (Volcengine family, model-override entry under `infistar`)

> Same gateway and same key; because the size contract differs and it rejects the `quality` parameter, it overrides the `infistar` entry in `generate.py` as `models: {doubao-seedream-5-0-260128: {...}}` (`size_rules: seedream_px`, `edit_format: json_images`, `default_quality: null`, `extra_params: {watermark: false, output_format: png}`). Invocation: `--provider infistar --model doubao-seedream-5-0-260128`.

- **Model**: `doubao-seedream-5-0-260128` = **Seedream 5.0 lite** (Volcengine native, infistar proxies to Volcengine Ark). The same family also has `doubao-seedream-4-0-250828` and others.
- **size (official)**: one of two — ① keyword `2k`/`3k`/`4k` (the model sizes itself from the prompt); ② explicit `WIDTHxHEIGHT`, total pixels **[2560×1440, 4096×4096]**, aspect ratio **[1/16, 16]**. Measured: `3840x2160` → **native output 3840×2160** (no crop).
- **quality**: **not supported** — passing any value (including `high`) gives **422** "the model does not support this parameter". The script omits the whole thing via `default_quality: null`.
- **watermark (official)**: **defaults to `true`** (adds "AI生成" in the bottom-right) — must be explicitly `false`. Measured: after passing `watermark=false` the output had no watermark.
- **output_format**: officially supports `png`/`jpeg` (5.0 lite only). Measured to **vary by path**: the `json_images` path takes effect (order 10 returned PNG); the multipart `/images/edits` path discards it (order 09 still returned JPEG). `generate.py`'s `image_size` now parses both PNG/JPEG headers.
- **Reference image: both paths measured to discard it → seedream on this channel is effectively text-to-image only**:
  - multipart `/images/edits` (order 09, 2026-09-24): the door/beast appearance matched the reference image in no way.
  - JSON `images` array base64 (order 10, 2026-09-24): likewise matched in no way (the door was still arched, the beast a generic quadruped).
  - Conclusion: infistar's seedream entry only declares `image-generation`, and neither reference-image path is translated upstream to Volcengine. **For reference-image consistency, switch model/channel** (e.g. heyroute's `nano-banana-pro`, `gemini-3-pro-image`).
- **Download**: returns a Volcengine TOS direct link (`ark-acg-cn-beijing.tos-cn-beijing.volces.com`), valid for 24h. **Measured that a direct `requests` connection occasionally hits SSL `UNEXPECTED_EOF`**, and `curl.exe` retried successfully — if the script download fails, you can curl that link manually.
- **Prompt length**: officially recommended ≤300 Chinese characters or 600 English words; measured that a long 1089-Chinese-character prompt still produced images (the mountain body/composition followed well), but for robustness the measured runs used a trimmed 354-Chinese-character version.
