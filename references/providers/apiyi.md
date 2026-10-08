# Provider Profile · APIYi (Seedream Channel)

> Fixed sections of a single-provider profile: Documentation Location / Authentication and Endpoints / Parameter Allowlist / Model Table / Size Rules / Response Protocol / Billing / Known Issues / Provider-Specific Parameters.
> Created (2026-09-25): sources = official docs (docs.apiyi.com) + live `GET /v1/models` measurements; **not yet** validated against a real image generation.

## Documentation Location

- Official docs (**authoritative**):
  - `https://docs.apiyi.com/api-capabilities/seedream-image/overview` (overview / pricing / technical specs)
  - `.../seedream-image/text-to-image`, `.../seedream-image/image-edit` (code samples / parameter quick reference)
  - `.../image-api-best-practices` (timeout / billing basis / base64 handling)
  - Append `.md` to any doc page URL to get its plain-text version; index at `https://docs.apiyi.com/llms.txt`
- API self-description (with Bearer): `GET /v1/models` — measured HTTP 200, 291 models, including `seedream-5-0-260128` (plus 5-0-flash / 5-0-pro / 4-5 / 4-0)
- Base: `https://api.apiyi.com/v1` (backup domain `https://vip.apiyi.com/v1`)

## Authentication and Endpoints

- Authentication: `Authorization: Bearer $APIYI_API_KEY`
- **Only one endpoint**: `POST /v1/images/generations` — text-to-image / single-image edit / multi-image fusion / batch sequence **all switch via request-body parameters**
- **There is no `/v1/images/edits`, and no `mask`** (completely different from the multipart edit path of OpenAI gpt-image-2)

## Parameter Allowlist

| Parameter | Values | Description |
|---|---|---|
| `model` | `seedream-5-0-260128` (= 5.0-lite), etc. | Required |
| `prompt` | text | Required; official recommendation ≤300 Chinese characters / 600 English words; in multi-image scenarios use "image 1/image 2" to indicate order |
| `image` | string array | **Reference image**: each element is a URL or `data:image/<lowercase-format>;base64,...`; **up to 10 images**; input reference images + output images ≤ 15 |
| `sequential_image_generation` | `disabled` / `auto` | Use `disabled` for single-image output; 5.0-pro / 5.0-flash **must not send it** (sending any value returns 400) |
| `sequential_image_generation_options.max_images` | 1–15 | Effective only in `auto` mode |
| `size` | tier or `WxH` | See below |
| `response_format` | `url` / `b64_json` | Default `url` (Seedream native default is URL) |
| `output_format` | `png` / `jpeg` | 5.0 series supports png; 4.5 / 4.0 only jpeg |
| `watermark` | boolean | **Must be explicitly `false`** (default varies by version / group) |
| `stream` | boolean | 5.0-lite supports; 5.0-pro / 5.0-flash return 400 when sent |

**Do not send**: `quality` (unsupported by this model, sending it returns 422/400), `n` (silently ignored, always 1 image), `seed` (ineffective on 4.x / 5.x).

## Model Table (live /v1/models measurements)

| model | Description | Price |
|---|---|---|
| `seedream-5-0-260128` | 5.0-lite (default for this channel; png/jpeg, image sequence, streaming) | $0.035/image |
| `seedream-5-0-flash-260915` | fast version (reference images not billed) | $0.018/call |
| `seedream-5-0-pro-260628` | pro version (about 2 minutes/image, no image sequence / streaming) | $0.12/call |
| `seedream-4-5-251128` | 4K + strong text rendering (jpeg only) | $0.04/image |
| `seedream-4-0-250828` | cheapest 4K (jpeg only) | $0.03/image |

## Size Rules (`size_rules: seedream_lite_px`)

- **Tiers**: `2K` / `3K` (5.0-lite — `seedream-5-0-260128` has **no 4K**); only 4.5 / 4.0 offer `4K`.
- **Exact pixels** (5.0-lite): total pixels ≈ [2560×1440, 3072×3072×1.1025 ≈ 10.4MP], aspect ratio [1/16, 16], **no multiple-of-16 restriction**.
- This skill uses a conservative upper bound `max_px = 10404496`; common values: 16:9 = **4096×2304**, 3:2 = **3744×2496**, 1:1 = **3072×3072**.
- ⚠ For the conflicting upper-bound specifications, see "Known Issues".

## Response Protocol (`response: json`)

- OpenAI-standard **synchronous** JSON: `{"data":[{"url": ...}], "usage": {...}}`; `url` is a BytePlus TOS temporary link (**expires in about 24h**, must be downloaded and stored immediately), or `b64_json` (pure base64, no `data:` prefix).
- No task ID; if the client disconnects the result is lost **but still billed** → allow ample timeout (Seedream recommends from 60s; 4K+hd takes about 30–60s).

## Billing Rules

- Billed by the actual number of images in `usage.generated_images`; **reference images are not billed extra**.
- **Not billed**: 400 / 403 (content moderation) / 429 / 503. **Still billed**: client disconnecting due to timeout.
- `n` has no effect; multiple images must use `sequential_image_generation: "auto"` (billed by actual image count).

## Known Issues

- **Prefer public URLs for reference images**: officially strongly recommended (BytePlus downloads directly from Singapore, request body only a few KB). base64 requires cross-border upload; 20–30MB will hit the origin's 600s request-body timeout → `400 Error when parsing request`, **and it will not automatically fall back to URL after failure**. When only base64 is possible: longest edge ≤2048, re-encode at q0.9, total across images ≤6MB — this prescription is codified as **`scripts/compress_refs.py`** (defaults `--max-edge 2048 --quality 90 --target-bytes 6MB`); after compression, feed the output paths to `--image`.
- **5.0-lite exact-pixel upper-bound specification conflict**: the official generic "exact pixel" section says [1280×720, 4096×4096], while the overview's Warning states "the 5.0 series has a higher lower bound and a lower upper bound" (5.0-lite lower bound ≈2560×1440). This profile takes Volcengine's 3K upper bound of ~10.4MP as the conservative boundary.
- **`n` silently ignored**: always returns 1 image (billed for 1).
- **URL expires in about 24h**: the server must download and store it immediately.
- **Not yet validated**: this channel has not yet produced a real image; the end-to-end behavior of reference images via the `image` array awaits first live confirmation.

## Provider-Specific Parameters

- `image` (reference-image array, URL or base64 data URI) — the key difference from infistar: the field name is the **singular `image`** (the infistar gateway uses the plural `images`), and `generate.py` distinguishes them by `ref_field`.
- `max_refs: 10` / `warn_ref_bytes: 6MB` / `max_ref_bytes: 20MB`: `generate.py` validates before sending — **more than 10 images is hard-rejected** (gateway `maxItems: 10`, the error-code table explicitly states 400); base64 total **>6MB only warns** (the official compression recommendation, **not** an error-code condition), **>20MB is hard-rejected** (the documented "do not send request bodies above 20MB" timeout red line).
- `layer_decomposition` (5.0-flash only: single image → background base image + multiple RGBA transparent layers, billed by output image count).
