# image-generation
[English](README.md) | **中文**

多厂商图片生成工作流技能（面向支持 `SKILL.md` 约定的编码 agent：OpenCode / WorkBuddy(CodeBuddy) / Claude Code 等）。

把「提示词完整性检查 → 参数平铺确认 → 脚本下单 → 交付核对」固化为一套可复用技能，支持：

- 多厂商统一入口（HeyRoute / Infistar / APIYi / 火山方舟），SSE 与 OpenAI 兼容 JSON 两种协议自动分流；
- 参考图（multipart edits / JSON base64 数组）与 mask 局部重绘；
- 浏览器蒙版编辑器（矩形 / 椭圆 / 多边形 / 画笔 / 橡皮、多选区、比例锁、撤销）；
- 完整测试：离线单测 + 浏览器 E2E + mutation 守门器。

## 安装

本仓库根目录即技能目录。把整个仓库放到目标 harness 的 skills 目录（目录名保持 `image-generation`）即可：

```bash
git clone --depth 1 <repo-url> <skills-dir>/image-generation
```

| harness | 项目级 skills 目录 | 用户级 |
|---|---|---|
| OpenCode | `.opencode/skills/` | - |
| WorkBuddy | `.workbuddy/skills/` | `~/.workbuddy/skills/` |
| CodeBuddy | `.codebuddy/skills/` | `~/.codebuddy/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |

也可用 git submodule 方式引入。

## 宿主适配

本 skill 最初为 OpenCode 编写。换到其他 harness 后有几处**会静默失效**的差异：工作目录变成**工程根**而不是技能目录；shell 是外部进程；**以 `-NoProfile -NonInteractive` 启动 shell 的 harness（WorkBuddy / CodeBuddy）读不到你在交互式 shell 里 `export` 的 key**——需用宿主 env 机制、`.image-generation/keys.env` 或 Windows 用户级注册表投递（会加载 profile 的环境如 OpenCode 无此问题）。

遇到「终端里能跑、agent 里跑不了」时，先看 `SKILL.md` 的「宿主适配」段（脚本绝对路径、解释器解析、密钥投递、mask_editor 后台化）。

## 项目定制层（可选）

通用库只含中性默认。把你的项目专属内容（默认规格 / 输出命名 / 画风模板 / 负向词 / 历史事故 / 决策来源）写进工程侧档案 `.image-generation/profile.md`：

```bash
mkdir -p .image-generation
cp <skills-dir>/image-generation/references/profile.example.md .image-generation/profile.md
# 编辑 .image-generation/profile.md
```

- 档案随**工程**入库，与技能安装位置无关，也不随技能更新被覆盖。
- 可用环境变量 `IMAGE_GENERATION_PROFILE` 指定其他路径。
- 宿主级 frontmatter 字段 `python`（解释器路径）与 `proxy`（出网代理）由 agent / `generate.py` 直接读取。
- 读取顺序：SKILL.md 通用默认 → 工程档案优先。

## 依赖

- Python 3.10+，`pip install -r requirements.txt`（`requests`、`Pillow`）
- 仅跑浏览器 E2E 时另需 Node + Playwright（见 `tests/README.md`）

## 快速开始

先设置对应厂商的 API key 环境变量（见表），再调用：

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

`--provider` 与 `--size` 均为必填（CLI 层必填；工作流默认值可来自工程档案）。查看全部参数：`"<SKILL_ROOT>/scripts/generate.py" --help`。

## 支持的厂商

| 厂商 (`--provider`) | 环境变量 | 端点/协议 | 档案 |
|---|---|---|---|
| `heyroute` | `HEYROUTE_API_KEY` | SSE | `references/providers/heyroute.md` |
| `infistar` | `INFISTAR_API_KEY` | OpenAI 兼容 JSON | `references/providers/infistar.md` |
| `apiyi` | `APIYI_API_KEY` | OpenAI 兼容 JSON | `references/providers/apiyi.md` |
| `volcengine` | `ARK_API_KEY` | OpenAI 兼容 JSON | `references/providers/volcengine.md` |

> 各厂商档案记录了实测行为与已知问题；部分模型标注为「未验证」，使用前请先小参数验证。

## 计费提醒

生图会**计费**。本 skill 的工作流强制「先列出该单完整参数并经用户确认，再发起计费请求」，并禁止批量测试。请始终遵守 `SKILL.md` 的确认门。

## 目录结构

```
SKILL.md        agent 读取的入口（工作流 + 核心规则）
references/     提示词清单、坐标编辑、厂商档案、项目档案示例
scripts/        generate.py（下单）、mask_editor.py（蒙版）、bbox_from_mask.py、
                compress_refs.py、convert_assets_to_jpg.py
tests/          离线单测 + 浏览器 E2E + mutation 守门器 + fixtures
```

## 测试

```bash
"<SKILL_ROOT>/tests/run_e2e.py" --unit-only   # 离线单测（零网络零费用）
"<SKILL_ROOT>/tests/run_e2e.py"               # 追加浏览器 E2E（需 Playwright）
"<SKILL_ROOT>/tests/mutation_check.py"        # 变异测试，验证套件真的会失败（较慢）
```

## License

MIT © 2026 Booomeii
