# Provider Profile · Volcengine Ark
**English** | [中文](volcengine.zh-CN.md)

> Section structure and how-to-add: see [`_template.md`](_template.md).
> Created (2026-09-25): sources = official docs + live `GET /api/v3/models` measurements (135 models); integrated and validated with image generation (see "Known Issues").

## Documentation Location

- Official docs: `https://www.volcengine.com/docs/82379/1356358` (Volcengine Ark) → Image Generation → "Doubao Seedream 5.0 pro Tutorial"
- API self-description: `GET /api/v3/models` — measured 200, 135 models, including `doubao-seedream-5-0-pro-260628`
- Base: `https://ark.cn-beijing.volces.com/api/v3`
- If this machine goes through an HTTP proxy, add `ark.cn-beijing.volces.com` to the direct-connection list (`NO_PROXY` / `no_proxy`), otherwise downloading Volcengine TOS direct links will time out

## Authentication and Endpoints

- Authentication: `Authorization: Bearer $ARK_API_KEY`
- Endpoint: `POST /api/v3/images/generations` (OpenAI-compatible; unified entry for text-to-image / reference-based generation)
- Models can be referenced by **model ID** (e.g. `doubao-seedream-5-0-pro-260628`) or **inference endpoint ID** (`ep-xxxx`); `/models` already lists model IDs, so they can be used directly

## Parameter Allowlist

| Parameter | Values | Description |
|---|---|---|
| `model` | `doubao-seedream-5-0-pro-260628`, etc. | Required |
| `prompt` | text | Required; ≤4000 tokens (about 2600 Chinese characters), recommended Chinese ≤300 characters |
| `image` | string[] | Reference image: URL or `data:image/<lowercase-format>;base64,...`; **up to 10 images**, each ≤30MB |
| `size` | ratio (`16:9` …) or `WxH` | Total pixel range `[921600, 4624220]`, ratio `[1/16, 16]` |
| `quality` | `1K` / `1.5K` / `2K` | **It is a resolution tier**, not low/medium/high → this skill uses pixel `size` and **does not send this parameter** |
| `response_format` | `url` / `b64_json` | Default `url` (Volcengine TOS, about 24h) |
| `watermark` | boolean | **Default `true`, must be explicitly `false`** |
| `sequential_image_generation` / `stream` / `tools` / `optimize_prompt_options` | — | **5.0 Pro supports none** (supported only by 4.0 / 4.5 / 5.0-lite) |

## Model Table (live /models measurements)

`doubao-seedream-5-0-pro-260628` (5.0 Pro: image quality priority, 1K/1.5K/2K, supports layer decomposition / interactive edit), `doubao-seedream-5-0-260128` (5.0-lite: 2K/3K/4K, supports image sequence / streaming), `doubao-seedream-5-0-flash-260915`, `doubao-seedream-4-5-251128`, `doubao-seedream-4-0-250828`.

## Size Rules (`size_rules: seedream_pro_px`)

- Exact pixels: total pixels `[921600, 4624220]`, ratio `[1/16, 16]`, **no multiple-of-16 restriction**, edge length >14px
- **Local protection upper bound `max_edge = 8192`** (built into `generate.py`'s `seedream_pro_px`, **the official specification has no such rule**): it serves only as a guardrail; since `8192² ≫ max_px`, it always triggers after the pixel window and in practice never intercepts a legal size
- Common 2K values: 1:1 = `2048x2048`, 3:2 = `2496x1664`, 16:9 = `2816x1584`, 21:9 = `3136x1344`
- **Colloquial-tier live measurement (2026-09-28)**: `16:9 1K` → `1824x1026`, **the actual output matches the request pixel-for-pixel** (`size_mismatch: false`)
- **5.0 Pro has no 4K** (max 2K; 4K only in 5.0-lite / 4.5 / 4.0)

## Response Protocol (`response: json`)

- `{"model":…, "created":…, "data":[{"url":…, "size":…}], "usage":{"generated_images":N, ...}}`
- `url` is a Volcengine TOS temporary link (expires in about 24h); this script downloads and stores it immediately upon receipt
- Synchronous call, no task ID

## Billing Rules

- Billed by the number of generated images; the user holds the "Seedream 5.0 pro lightweight creation pack" (prepaid quota)
- Whether a single-image failure / parameter error is billed is subject to the Volcengine console bill

## Known Issues

- ~~Not yet validated with image generation~~ → **Live-tested (2026-09-25)**: text-to-image and "reference image + `image` array" work end to end; reference images are followed well (gate / beast / beast nest consistent with the reference).
- **Interactive edit (coordinate selection) is live-tested and working**: mechanism and usage are in `references/coordinate-edit.md`. Key points — coordinates are **not an API field**, but are written into the prompt as `Image N x1 y1 x2 y2` (normalized 0–999); **it is good at "in-region replacement/redraw", not at "precise proportional scaling"**; the companion workflow uses `mask_editor.py` for selection + `bbox_from_mask.py` to invert the coordinates.
- `quality` semantics differ from the OpenAI family (resolution tier); this skill avoids it (does not send `quality`, uses pixel size)
- 5.0 Pro does not support image sequence / streaming / web access (only 5.0-lite supports them)
- Content moderation: Byte's own model; its moderation criteria differ from OpenAI/Google (live tests did not block beast subject matter)

## Provider-Specific Parameters

- `image` (reference-image array, **singular name**) — consistent with the seedream entry in apiyi
- `watermark` defaults to `true`, must be explicitly disabled
