# image-generation
**English** | [中文](README.zh-CN.md)

Multi-provider image generation workflow skill (for coding agents that follow the `SKILL.md` convention: OpenCode / WorkBuddy(CodeBuddy) / Claude Code, etc.).

It consolidates "prompt completeness check → parameter flattening confirmation → script ordering → delivery verification" into a reusable skill that supports:

- A unified multi-provider entry point (HeyRoute / Infistar / APIYi / Volcengine Ark), with automatic routing between two protocols: SSE and OpenAI-compatible JSON;
- Reference images (multipart edits / JSON base64 arrays) and mask-based local repainting;
- Browser mask editor (rectangle / ellipse / polygon / brush / eraser, multiple selections, aspect-ratio lock, undo);
- Full testing: offline unit tests + browser E2E + mutation gate.

## Installation

The repository root is the skill directory. Simply place the entire repository into the target harness's skills directory (keeping the directory name `image-generation`):

```bash
git clone --depth 1 <repo-url> <skills-dir>/image-generation
```

| harness | project-level skills directory | user-level |
|---|---|---|
| OpenCode | `.opencode/skills/` | - |
| WorkBuddy | `.workbuddy/skills/` | `~/.workbuddy/skills/` |
| CodeBuddy | `.codebuddy/skills/` | `~/.codebuddy/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |

It can also be imported as a git submodule.

## Project customization layer (optional)

The generic library contains only neutral defaults. Put your project-specific content (default specs / output naming / art style templates / negative words / historical incidents / decision sources) into the project-side profile `.image-generation/profile.md`:

```bash
mkdir -p .image-generation
cp <skills-dir>/image-generation/references/profile.example.md .image-generation/profile.md
# 编辑 .image-generation/profile.md
```

- The profile is committed with the **project**, independent of where the skill is installed, and is not overwritten by skill updates.
- You can use the environment variable `IMAGE_GENERATION_PROFILE` to specify another path.
- Read order: SKILL.md generic defaults → project profile takes precedence.

## Dependencies

- Python 3.10+, `pip install -r requirements.txt` (`requests`, `Pillow`)
- Running browser E2E additionally requires Node + Playwright (see `tests/README.md`)

## Quick start

First set the API key environment variable for the corresponding provider (see the table), then call:

```bash
export HEYROUTE_API_KEY=...
python scripts/generate.py \
  --provider heyroute \
  --model gpt-image-2 \
  --size "16:9 1K" \
  --quality high \
  --prompt-file prompt.txt \
  --out out.jpg
```

`--provider` and `--size` are both required (required at the CLI layer; workflow defaults may come from the project profile). To view all parameters: `python scripts/generate.py --help`.

## Supported providers

| provider (`--provider`) | environment variable | endpoint/protocol | profile |
|---|---|---|---|
| `heyroute` | `HEYROUTE_API_KEY` | SSE | `references/providers/heyroute.md` |
| `infistar` | `INFISTAR_API_KEY` | OpenAI-compatible JSON | `references/providers/infistar.md` |
| `apiyi` | `APIYI_API_KEY` | OpenAI-compatible JSON | `references/providers/apiyi.md` |
| `volcengine` | `ARK_API_KEY` | OpenAI-compatible JSON | `references/providers/volcengine.md` |

> Each provider profile records measured behavior and known issues; some models are marked "unverified", so validate with small parameters before use.

## Billing reminder

Image generation is **billed**. This skill's workflow enforces "first list the complete parameters of the order and obtain user confirmation, then issue the billed request", and forbids batch testing. Always follow the confirmation gate in `SKILL.md`.

## Directory structure

```
SKILL.md        agent 读取的入口（工作流 + 核心规则）
references/     提示词清单、坐标编辑、厂商档案、项目档案示例
scripts/        generate.py（下单）、mask_editor.py（蒙版）、bbox_from_mask.py、
                compress_refs.py、convert_assets_to_jpg.py
tests/          离线单测 + 浏览器 E2E + mutation 守门器 + fixtures
```

## Tests

```bash
python tests/run_e2e.py --unit-only      # 离线单测（零网络零费用）
python tests/run_e2e.py                  # 追加浏览器 E2E（需 Playwright）
python tests/mutation_check.py           # 变异测试，验证套件真的会失败（较慢）
```

## License

MIT © 2026 Booomeii
