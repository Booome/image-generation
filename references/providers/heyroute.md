# Provider Profile · HeyRoute
**English** | [中文](heyroute.zh-CN.md)

> Section structure and how-to-add: see [`_template.md`](_template.md).

## Document Locations

- **Official skill repository (authoritative protocol reference)**: `https://github.com/heyroute-ai/skills` — inside the repository, `image-gen/SKILL.md` + `image-gen/scripts/heyroute_image.py` (zero-dependency reference implementation) + `image-gen/references/prompting.md` (prompting methodology). **These are files in the upstream repository; they do not exist in this skill directory.** For uncovered functionality, **read here first**.
- Help center: `https://heyroute.ai/help` (SPA, requires browser rendering)
- API self-description (with Bearer): `GET /v1/models`
- Invalid-parameter probe: a parameter error before SSE returns a plain JSON 400 with the full rules (**not billed**); but note that **lenient parameters may start generating directly and get billed** — only use the probe on fields known to be rejected (such as size format).
- Base: `https://heyroute.ai/v1` (OpenAI-compatible)

## Authentication and Endpoints

- Authentication: `Authorization: Bearer $HEYROUTE_API_KEY`; also recommended to include `Accept: text/event-stream`
- `POST /v1/images/generations` — JSON, text-to-image
- `POST /v1/images/edits` — `multipart/form-data`, image editing / reference image; `image` is the file field, **for multiple images repeat the same-named `image` field** (the first one is the subject image); optional `mask` PNG mask

## Parameter Allowlist (passing anything else gets 400 or is ignored)

| Parameter | Values | Notes |
|---|---|---|
| `model` | `gpt-image-2` (the official skill has only this one); see the model table below for the rest | **Measured**: `gpt-image-2`, `nano-banana-pro`, `gemini-3-pro-image`; the remaining ids are in the model table below — probe before use if not measured |
| `prompt` | text | required |
| `n` | `1` | **only 1 image supported** |
| `size` | `auto` or `WIDTHxHEIGHT` | see the size rules below |
| `quality` | `low` / `medium` / `high` / `auto` | **must be passed, defaults to high** (this skill defaults to high) |
| `stream` | `true` | protocol declaration, always passed |

**Do not pass**: `response_format`, `background`, `output_format`, `style`, etc. (ignored/filtered, the result is always b64).

## Model Table (per /v1/models, 2026-09-24)

The official skill covers only `gpt-image-2`; the rest are as measured-listed by /v1/models (`owned_by` all show openai). **Except for those marked as measured, check the official skill or probe before use**:

| Model | Status |
|---|---|
| `gpt-image-2` | Covered by the official skill; upstream native cap ~1.57MP (see Known Issues) |
| `gpt-image-2.5` | not verified |
| `nano-banana-pro` | **Measured** (= Google Gemini 3 Pro Image) — best reference-image adherence, but resolution is only 1K; see the dedicated section below |
| `gemini-3-pro-image` | **Measured (2026-09-28)**: `/images/edits` usable; `size=16:9 4K` (`3840x2160`) → **actually returns `1376x768`**, same 1K behavior as `nano-banana-pro` (size only sets the aspect ratio) |
| `nano-banana-2` | not verified (presumed = Gemini 3.1 Flash Image) |
| `gemini-3.1-flash-image` | not verified |
| `flux-klein-2` | not verified |
| `grok-imagine-image` | not verified |

### Gemini Image Family (nano-banana-pro = Gemini 3 Pro Image)

> Documented 2026-09-24 (11th order measured + Google official docs). heyroute-side ids: `nano-banana-pro`, `gemini-3-pro-image`, `nano-banana-2`, `gemini-3.1-flash-image`.

**Official specs (Google, `ai.google.dev` / Vertex)**
- Resolution: **1K / 2K / 4K** (4K marked Preview); **the native parameters are `aspectRatio` + `imageSize` (`"1K"/"2K"/"4K"`), not `WIDTHxHEIGHT`**
- Aspect ratios: 1:1, 3:2, 2:3, 3:4, 4:3, 4:5, 5:4, 9:16, **16:9**, 21:9 (some platforms additionally offer 1:4/4:1/1:8/8:1)
- Reference images: up to 14 (6 at high fidelity)
- Output tokens: 1K/2K→1120, 4K→2000 (billed by pixels); input is 560 tokens per image

**heyroute measured (`nano-banana-pro`, 2026-09-24)**
- Call: `POST /v1/images/edits` (multipart with repeated `image` fields) + `size: "3840x2160"` + `quality: "high"` + `stream: true` — **neither `quality` nor `size` was rejected** (no 400).
- **The reference image takes effect and adherence is currently the best**: the gate came out as a **rectangular double-leaf with louvered vent** (matching the reference), the beast as a spiked dark-red giant beast (matching the reference), the beast nest containing rebar/skulls/**honeycomb metal fragments**.
- **Resolution is only 1K**: requesting `3840x2160` (8.29MP) → **actually returns `1376x768` (1.06MP, 16:9)**. That is, heyroute's `size` for the Gemini family **only sets the aspect ratio, `imageSize` defaults to 1K, and the pixel count is ignored**.
- **Unknown**: how to request 2K/4K — OpenAI's `size` field has no `imageSize` slot; whether heyroute exposes a parameter to set imageSize (name unknown) **is undocumented**. A size probe would **be billed directly** (lenient model) and cannot be tried for free.

**Conclusion**: for "reference-image consistency" choose the Gemini family; for "4K" this path is currently blocked (need to first find heyroute's imageSize parameter).

## size Rules (`size_rules: pixel_window`, 400 error text measured verbatim)

`auto` or `WIDTHxHEIGHT`: both sides multiples of 16, longest side ≤ 3840, ratio ≤ 3:1, total pixels ∈ [655360, 8294400].
> The line above is **the upstream gateway's rule** (an objective record). **It is no longer validated locally**: since 2026-09-29, side-multiple validation was removed for all providers; `WIDTHxHEIGHT` only checks longest side / ratio / pixel window, and odd side lengths are handed to the API as-is for it to decide.
Common tiers (official skill): `1024x1024` (fastest) / `2048x2048` / `2880x2880` (largest square) / `1536x1024` / `1024x1536` / **`3840x2160` (4K landscape)**.

### Colloquial tier conversion (short side = 1024×K, exact ratio, clamped to upper limit; implemented by `resolve_size()`)

| Tier | Conversion |
|---|---|
| 3:2 1K | 1536x1024 |
| 3:2 2K | 3072x2048 |
| 3:2 4K | 3504x2336 (clamped; **whether the image is truly 4K is unverified, see Known Issues**) |
| 16:9 1K | 1792x1008 |
| 16:9 4K | 3840x2160 (official commonly-used 4K landscape tier) |

Reference: the infinite-canvas project's 3:2 4K tier is `3520x2336` (legal as a multiple of 16, ratio 1.507).

## Response Protocol (`response: sse`, different from OpenAI official)

- **SSE always**: HTTP 200 + `text/event-stream`, whether or not stream is passed; **do not use the OpenAI SDK's synchronous JSON methods**
- Event sequence: `started → heartbeat（every 15s）→ completed | error → done → disconnect`; generation typically takes 30–120s
- The success image is in the **`completed` event's `data[0].b64_json`** (PNG base64)
- **HTTP 200 does not mean success**: business errors are in the `error` event (the fee is automatically refunded); only authentication/balance/parameter errors before SSE are plain JSON 4xx
- After saving, **read the image metadata to verify the actual pixels** (the actual size is whatever is returned)

## Billing Rules

- Generation failure (error event / pre-charge failure) is **automatically refunded**
- **After successful generation, disconnecting mid-stream still bills** — you must read the stream to completion before exiting
- 402 = insufficient balance; for 429 wait per `Retry-After`

## Error Reference (official skill)

| Symptom | Meaning | Handling |
|---|---|---|
| HTTP 401 | invalid/missing token | check HEYROUTE_API_KEY |
| HTTP 402 `insufficient_user_quota` | insufficient balance | prompt to top up |
| HTTP 403 | group has not opened the model / token allowlist | check the token group |
| HTTP 400 parameter class | size/n/quality non-compliant (size errors include the full rules) | fix per the allowlist |
| HTTP 400 `wrong_image_api_path` | Base URL missing `/v1` | fix per `correct_url` |
| HTTP 429 | rate limiting/cooldown | wait per Retry-After |
| SSE `error` | generation failure (upstream/content policy) | display the message; **already refunded** |

## Known Issues

- **[Confirmed] Measured pattern for high-resolution tiers (2026-09-23, gpt-image-2 + quality=high + stream)**:
  | Requested size | Result | Duration |
  |---|---|---|
  | `3504x2336` (3:2 4K conversion) | downgraded, actually returns 1536x1024 (twice) | ~40s |
  | `3520x2336` | connection-layer hang (not billed, server never started) | — |
  | `3840x2160` (first time) | connection-layer hang (not billed) | — |
  | **`3840x2160` (retry after connection fix)** | **actually returns `1672x941`** (16:9 ratio correct, not a multiple of 16, **total pixels 1.573MP ≈ same budget as 1536x1024**) | ~40s |
  | `1536x1024` (1K 3:2) | success | ~40s |
  **Root cause (empirically confirmed)**: **the upstream gpt-image-2 always generates to a pixel budget of ~1.57MP (1536x1024 level); the requested size only determines the aspect ratio and does not increase pixels** — `3840x2160`→1672x941 (16:9, same pixels) and `3:2`→1536x1024 are mutual ironclad proof. **Native 4K is a dead end on this path (empirically confirmed)**; the gateway's multiple-of-16 / 3840 rules are only input validation and do not represent the upstream output size.
  **Three-layer fast connection failure** (generate.py, derived from the official skill: heartbeat 15s, official script timeout 120):
  ① preflight `GET /models` (8s/15s, zero cost); ② POST `timeout=(8, 60)`; ③ overall stream cap 240s (`--timeout`). The three layers proved effective: connection problems surface within 8–60s.
  **Viable route (decided by the user)**: heyroute/gpt-image-2 generates per its **native cap of ~1.57MP (3:2 = 1536x1024)**; **no interpolation upscaling is used**; for native 4K, wait for a **provider that newly adds 4K support later** (at which point follow the skill's three-step provider documentation process); or switch to another heyroute model (unverified, must be confirmed by the user before ordering).
  (The old hypothesis "missing quality/stream" was disproven on 2026-09-23 after the parameters were supplied.)
- **[Closed] Probe risk**: for lenient models (nano-banana/flux/gemini), sending an invalid size **is not rejected and directly starts generating and billing** — the probe is only permitted for gpt-image-2's size-class parameters.

## Provider-Specific Parameters

- `mask` (optional PNG mask for edits, **`--mask` is implemented and measured**): transparent area = repainted, opaque area = preserved at the pixel level.
  **Measured conclusion (definitive)**: ① `edits`' `size` **must explicitly match the input frame** (e.g. `16:9 1K`); passing `auto` makes the upstream fall back to a 1:1 **square output**; ② mask+edits is a **viable path for ratio/geometry correction** — a geometric scaling instruction worked for the first time in this mode (versus 0/9 complete failure with text-only locking), invariants outside the mask were executed well, and in-region completion was natural; ③ a single round of scaling may be under-executed → **progressive iteration** (repeat the invariants in each round's prompt + "continue scaling on top of what is already scaled, no rebound").
