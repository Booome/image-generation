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

## Host adaptation

This skill was originally authored for OpenCode. Other harnesses differ in ways that silently break it: the working directory is the **project root** rather than the skill directory, and the shell is an external process. Harnesses that launch their shells with `-NoProfile -NonInteractive` (WorkBuddy / CodeBuddy) do not see keys exported by your interactive shell — deliver them via the host's env mechanism, a `.image-generation/keys.env` file, or the Windows user-level registry. (Environments that do load the profile, e.g. OpenCode, are unaffected.)

See the **Host adaptation** section in `SKILL.md` for the concrete rules (absolute script paths, interpreter resolution, key delivery, backgrounding the mask editor) before troubleshooting "it works in my terminal but not in the agent".

## Project customization layer (optional)

The generic library contains only neutral defaults. Put your project-specific content (default specs / output naming / art style templates / negative words / historical incidents / decision sources) into the project-side profile `.image-generation/profile.md`:

```bash
mkdir -p .image-generation
cp <skills-dir>/image-generation/references/profile.example.md .image-generation/profile.md
# edit .image-generation/profile.md
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
"<PYTHON>" "<SKILL_ROOT>/scripts/generate.py" \
  --provider heyroute \
  --model gpt-image-2 \
  --size "16:9 1K" \
  --quality high \
  --prompt-file prompt.txt \
  --out out.jpg
```

`--provider` and `--size` are both required (required at the CLI layer; workflow defaults may come from the project profile). To view all parameters: `"<SKILL_ROOT>/scripts/generate.py" --help`.

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
SKILL.md        agent entry (workflow + core rules)
references/     prompt checklist, coordinate editing, provider profiles, project-profile example
scripts/        generate.py (ordering), mask_editor.py (mask), bbox_from_mask.py,
                compress_refs.py, convert_assets_to_jpg.py
tests/          offline unit tests + browser E2E + mutation gate + fixtures
```

## Tests

```bash
"<SKILL_ROOT>/tests/run_e2e.py" --unit-only   # offline unit tests (no network, no cost)
"<SKILL_ROOT>/tests/run_e2e.py"               # adds browser E2E (needs Playwright)
"<SKILL_ROOT>/tests/mutation_check.py"        # mutation test, proves the suite can fail (slow)
```

## License

MIT © 2026 Booomeii
