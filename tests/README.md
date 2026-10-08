# image-generation Toolchain Tests
**English** | [中文](README.zh-CN.md)

`python run_e2e.py` runs everything in one command: **offline unit tests** (multiple groups, zero network, zero cost) → **headless Chromium interaction assertions** → **mask pixel verification + `bbox_from_mask.py` integration**. Exit code 0 = all green.

> The assertion inventory is defined by each test file; this document does not hard-code counts (a hard-coded number is bound to drift as the code changes). To verify "the tests really do fail", run `python mutation_check.py` — it deliberately breaks the implementation and requires the suite to go red.

## One-time setup

```bash
cd tests
npm install                        # playwright (node_modules is already ignored by .gitignore)
npx playwright install chromium    # ~115MB, downloaded only once
```

## Running

```bash
python run_e2e.py                              # default base image tests/fixtures/sample.jpg
python run_e2e.py --unit-only                  # run offline unit tests only (no Chromium needed)
python run_e2e.py --image <path> --keep-mask out.png
```

## Offline unit tests (multiple groups, no node needed)

| File | Coverage |
|---|---|
| `test_generate.py` | `write_output` format contract (`.png` emits PNG, everything else emits JPEG, **an existing JPEG is not re-encoded**, with alpha falls back to PNG, no extension appends `.jpg`), `image_size` header parsing, `detect_format`, `configure_stdio` respects an explicit env, `_size_ok` and `_explicit_errors` share one source |
| `test_sizes.py` | 7 tiers/explicit sizes × 4 providers: ratio correct, rule legal, **must be explicitly annotated when clamped by the cap**; illegal values are always rejected with candidates and a "no request sent" declaration |
| `test_assets.py` | `compress_refs`: base64 length, `fit()` converges to budget, CLI-reported size **equals the size written to disk**, non-zero exit when the budget is unreachable; `convert_assets_to_jpg`: converts only what should be converted, keeps originals by default, `--skip`, `--delete-originals`, `--dry-run`, symlink retargeting |
| `test_request.py` | Stubs `requests.post`: endpoint, fields, types, and the presence/absence of SSE and `quality` for the three request shapes (multipart edits / JSON generations / JSON `image` array) |
| `test_contracts.py` | Cross-file contracts: every provider has a profile, PROVIDERS fields are read, scripts↔SKILL.md consistency, no real user paths in committed files |
| `test_semantics.py` | Existing semantics regressions: mask_editor saves alpha, bbox threshold, generate exit code, `--size` required, compress/convert default behavior |
| `test_hygiene.py` | Resources and cleanup: leftover temp dirs/workspaces, port release, exit 1 on failure paths |

## Browser E2E (real Chromium)

| File | Role |
|---|---|
| `run_e2e.py` | Orchestration: run offline unit tests → start the server (auto-select a free port) → run browser assertions → verify the mask |
| `e2e_server.py` | Starts `mask_editor`'s HTTP service headlessly (**replaces `webbrowser.open` with a no-op, never pops up a real window**) |
| `e2e.js` | playwright interaction assertions (counts are defined by e2e.js) |
| `verify_mask.py` | Mask after save: size, bbox ratio, inside/outside alpha, coverage + `bbox_from_mask.py` integration |

Coverage: draw → ratio lock → drag corner/edge/inside-box → numeric input (H derived from ratio, lock disabled) → **arrow keys swallowed while an input is focused** (prevents typing from moving the box) → arrow-key nudge (box 1px / Shift 10px; after clicking a handle, push/pull that edge) → Esc cancels the handle → Ctrl+Z undo → Ctrl+wheel zoom / middle-button pan / fit → ellipse uses the same ratio lock → save → mask verification.

## Known limits

- `e2e.js`'s coordinate tolerance scales with `1 / view.k` (screen rounding amplifies the error up to in-image pixels).
- Chromium is ~115MB, cached only locally in `ms-playwright`, and is not committed with the repo.
- Offline unit tests are independent of each other and can each be run separately with `python test_xxx.py`.
