---
name: image-generation
description: 多厂商图片生成工作流（HeyRoute 及后续 OpenAI 兼容厂商）：提示词八段完整性检查、参数平铺确认、Python 脚本下单（含 3:2 4K 等口语档位自动换算）、SSE/JSON 取回、按提示词逐项核对交付。凡用户要求生成图片、出图、生图、画一张、做配图、参考图出新图、换姿态/状态重绘，或点名 gpt-image、nano-banana、flux、gemini image 等图像模型时，即使未提到厂商名或本 skill 名字，也一律使用本 skill。
allowed-tools: Read, Write, Bash
---

# 图片生成（image-generation）

多厂商图片生成工作流：提示词完整性检查 → 参数平铺确认 → 脚本下单 → 交付核对。

## 项目定制层（可选）

本 skill 的通用默认可被**工程档案**覆盖；读取顺序为「本文件的通用默认 → 若存在工程档案则其内容补充并优先」。

- 档案路径（相对 workspace 根）：`.image-generation/profile.md`；若设置了环境变量 `IMAGE_GENERATION_PROFILE` 则以其为准。
- 档案为单个 markdown：顶部 YAML frontmatter 承载 `default_provider` / `default_model` / `default_size` / `output_naming` / `python` / `proxy`；正文承载「画风模板 / 负向词 / 历史事故 / 已定决策来源」。
- 宿主级字段：`python`（解释器绝对路径，由 agent 解析后用作 `<PYTHON>`）与 `proxy`（出网代理，**由 `generate.py` 自己读取**：`--proxy` > `$IMAGE_GENERATION_PROXY` > 档案 `proxy:`）。其余默认值由 agent 依档案填入参数表。**档案随工程入库，`proxy` 不要写带凭据的 URL**（凭据类代理走 `$IMAGE_GENERATION_PROXY` / `--proxy`）。
- 中性示例见本 skill 的 `references/profile.example.md`（不代表任何真实项目）。
- 档案位于工程侧、随工程入库；本 skill 仓库不含该文件。

## 宿主适配（WorkBuddy / CodeBuddy / Claude Code / OpenCode）

通用工作流不变，但**换 harness 后有几处硬差异，每单都要遵守**（原版在 OpenCode 下写作，那里 cwd 恰好等于 skill 目录）：

1. **脚本一律用绝对路径调用**。多数 harness（WorkBuddy / CodeBuddy / Claude Code）的工作目录是**工程根**或会话目录，不是本 skill 目录——照抄 `python scripts/generate.py` 会直接「can't open file」。正确做法：把**本 SKILL.md 所在目录**作为 `<SKILL_ROOT>`，再拼绝对路径。

```bash
"<PYTHON>" "<SKILL_ROOT>/scripts/generate.py" --provider heyroute --size "1:1 1K" \
  --prompt-file prompt.txt --out "<工程内输出路径>/xxx.jpg"
```

   **只有 `--out` / `--image` / `--mask` / `--prompt-file` 走工程侧路径，脚本本体永远走 `<SKILL_ROOT>/scripts/`。**

2. **解释器必须带依赖**（`requests` + `Pillow`，见 `requirements.txt`）。按以下顺序解析 `<PYTHON>`，**取第一个 `-c "import requests, PIL"` 能通过的解释器**：
   - 环境变量 `IMAGE_GENERATION_PYTHON`（跨 harness 通用，推荐）
   - 工程档案 `.image-generation/profile.md` frontmatter 的 `python` 字段（示例见 `references/profile.example.md`）
   - 裸 `python`
   三者都缺依赖时：**不要擅自 pip install 到系统 Python**，向用户报告并给出在 venv 里 `pip install -r "<SKILL_ROOT>/requirements.txt"` 的指引。

3. **`mask_editor.py` 会长期占住前台**（`serve_forever()`，保存成功后约 1 秒自行 shutdown）。因此：
   - 必须**以后台方式启动**（后台任务或 `&`），否则这次工具调用会一直不返回；
   - 启动后它自己会尝试 `webbrowser.open()`；若当前环境拉不起浏览器（远程会话 / 沙箱 / 无 GUI），**把打印出来的 `http://127.0.0.1:<port>/` 交给用户手动打开**，不要因此判定失败；
   - 只监听 `127.0.0.1`，端口被占会自动退到 `port+1`。

4. **输出编码**：两层策略（脚本自愈 + OpenCode 可选插件）见「工作流程」第 4 步；核心是脚本自带第 1 层自愈，任何 harness 下都成立。
5. **密钥投递**：`read_env()` 依次读「进程环境 → Windows 用户级注册表 → 工程侧 `.image-generation/keys.env`（可选，最后兜底）」。**以 `-NoProfile -NonInteractive` 启动 shell 的 harness（如 WorkBuddy / CodeBuddy）读不到交互式 shell（PowerShell profile）里 `$env:` 设的值**——这类 harness 需用宿主 env 机制（如 `settings.json` 的 `env`）、`keys.env` 或注册表投递；会加载 profile 的环境（如 OpenCode）则无此问题。**变量存在但值为空 = 未配置**。
   - `keys.env` 为纯文本 `NAME=VALUE`（**必须是 `NAME=VALUE`，带 `export ` 前缀的行不会被识别**；`#` 注释），默认路径 `.image-generation/keys.env`（**相对当前工作目录**；建议用环境变量 `IMAGE_GENERATION_KEYS_FILE` 显式指定绝对路径）；**该文件不要入库**。
6. **超时对齐**：`generate.py --timeout` 默认 240s（sync-JSON 厂商要等整张图生成完），而多数 harness 的前台命令默认超时更短（如 WorkBuddy 约 120s）——**sync-JSON 厂商一律以后台任务方式跑**，或把宿主的命令超时调到 ≥300s，否则前台拿不到结果、需另行轮询。
7. **出网代理**：有些 harness 会把出网流量注入到一个"直连出口"的沙箱代理（`HTTP_PROXY=127.0.0.1:<随机端口>`），它**不链接你自己的代理**——此时被墙的厂商 API / 图片 CDN 域名会表现为超时失败而非 HTTP 错误码。用档案 `proxy:`（或 `$IMAGE_GENERATION_PROXY` / `--proxy`）显式指定代理，见「项目定制层」。

## 工作流程

1. **确定厂商**：默认取工程档案 `.image-generation/profile.md` 的 `default_provider`（无档案或未配置时为 `heyroute`）；用户点名其他厂商时查 `references/providers/<厂商>.md`——**没有档案就先建档案再下单**（建档步骤见下）。
2. **准备提示词，过完整性清单**：按 `references/prompt-checklist.md` 逐段检查。凡是此前讨论定过的内容（开合方式、比例锁死、正反面特征、单张/组合版式），必须显式写进提示词，遗漏即返工——模型不会替你记住对话。
3. **平铺参数表，等用户确认**：通用字段（模型、端点、**提示词全文**、参考图路径、比例与分辨率、张数、输出路径）+ **该厂商档案里的特有字段**（认证变量名、厂商特有参数、档位换算结果如 `3:2 4K → 3504x2336`）。直接问「是否合适」，不用选项控件、不只列差异。用户确认前**不得发起任何计费请求**。
   **分辨率不合规处理（所有厂商同规则）**：必须**指出具体错误点**（违反哪条规则、原值多少）→ **推荐临近合法分辨率**（保比例最近值 + 厂商官方常用档）→ **等用户选定并重新确认**；**绝不自动替换、绝不静默改参数生成**。脚本 `check_size_or_die` 已强制此行为（不合法直接退出、不发请求）；**档位写法**（如 `16:9 1K`）若低于该渠道像素下限，同样会退出并给出候选，不会替你改档。
4. **下单**：

```bash
"<PYTHON>" "<SKILL_ROOT>/scripts/generate.py" \
  --provider heyroute \
  --model gpt-image-2 \
  --size "16:9 1K" \
  --quality high \
  --prompt-file prompt.txt \
  --image 参考图.png \
  --out out.jpg
```

   **输出编码（中文不乱码）＝两层，本 skill 只依赖第 1 层：**
   - **第 1 层 · 脚本自愈（自带，任何机器、任何宿主、不装任何东西都成立）**：`generate.py` 用 `configure_stdio()` 自判断——**显式设了 `PYTHONIOENCODING` / `PYTHONUTF8` 就按它来**；**交互式控制台不动**（Windows 走 `WriteConsoleW`，Unix 本就 UTF-8）；**管道输出默认 UTF-8**（宿主 locale 只是本机偏好、不是消费者的契约，故不继承）。**不改动任何系统或宿主设置（代码页 / locale / profile / 环境变量一律不碰）**。→ 在**没装插件的陌生机器**上，中文报错与结果 JSON 同样正确。
   - **第 2 层 · 宿主侧（可选加分项，不假设它存在）**：若恰好运行在**装了 `opencode-windows-encoding@5.0.0` 的 opencode** 里，它会给每条 bash 命令注入 UTF-8，使**调用方 shell 自己打印的中文**（`Get-ChildItem` 出来的中文文件名等）也正常——**这层 Python 管不到**。**没有它不影响本 skill 任何功能**，只是没人兜这最后一层。（`opencode-windows-encoding` 是 **OpenCode 可选**加成，其他 harness 无需关心。）
   - **两层兼容**：插件注入 `PYTHONIOENCODING=utf-8` 时 `configure_stdio()` 走早退，结果仍为 UTF-8（实测共存无冲突）。
   - 每单同时落盘 `<输出名>.json`（与 `--out` 同名、扩展名换成 `.json`；UTF-8），控制台万一被宿主编码破坏时以该文件为准。

   `--size` 接受 `WIDTHxHEIGHT` 或口语档位（`3:2 1K`、`4K 3:2`——短边=1024×K、精确比例、16 倍数、超限自动钳制并回显；**`auto` 被硬禁**）。**`WIDTHxHEIGHT` 只做长边/比例/像素窗校验，不做 16 倍数校验——奇数边长（如 infistar 实测的 `1672x941`）直接原样交给 API 判断**；档位换算按各 provider 的 `edge_multiple` 步长取整（seedream 系为 `None`，不取整）。`--quality` 默认 `high`（heyroute 白名单必传项；provider 顶层或 `models` 覆盖表声明 `default_quality: null` 则整条省略）。参考图传递：无 `--image` 走 generations；带 `--image` 默认走 edits（多图重复 `image` 字段），**模型若声明 `edit_format: json_images`（如 seedream）则改为把参考图以 base64 放进 generations 的 JSON `image`/`images` 数组（字段名由 provider 的 `ref_field` 决定）**。**需要 mask 局部重绘时**：先运行 `"<PYTHON>" "<SKILL_ROOT>/scripts/mask_editor.py" --image <主体图> --out <mask.png>`（**后台启动**，见「宿主适配」第 3 条）弹出浏览器窗口，用矩形/椭圆/多边形/画笔/橡皮绘制重绘区（红色显示、羽化导出），保存后文件即为该单 mask；**每单的 mask 必须基于当单主体图重新生成/确认，并把可视化 check 展示给用户**（`json_images` 厂商不支持 mask，脚本会报错）。API key 读该厂商的环境变量（见档案）。**协议细节与官方参考实现见 `references/providers/heyroute.md` 与官方仓库 `github.com/heyroute-ai/skills`。**

5. **交付核对**：读回图片，对照提示词必要项与禁令逐项核对（开合方式、比例、禁物），连同**实际分辨率**回报。**任何错误/不符（分辨率偏差、流超时、连接失败等）：先向用户报告并等处理指示，绝不自作主张回写或重试**；仅当用户确认属**确定性问题**（可复现、已证实的模式）时，才把结论记入厂商档案「已知问题」——随机/偶发问题不记录。

## 协议要点（以厂商档案为准）

各厂商的 size 规则 / 响应协议 / 扣费 / 特有参数，**一律以 `references/providers/<厂商>.md` 与脚本 `check_size_or_die` 为准**，本文件不复述数值。通用铁律：**`auto` 硬禁**、**不做 16 倍数校验**（本地只查长边/比例/像素窗）、分辨率不合规只报错+推荐不自动改、一切计费调用先确认。heyroute 的固定 SSE、断流仍扣费等细节见 `references/providers/heyroute.md`。

## 参考文件

| 文件 | 用途 | 何时读 |
|---|---|---|
| `references/prompt-checklist.md` | 提示词八段清单 + 已定决策查证来源 | 每次准备提示词时 |
| `references/coordinate-edit.md` | Seedream 交互编辑：坐标写法（`Image N x1 y1 x2 y2`，归一化 0–999）、mask_editor+bbox_from_mask 流程、实测能力边界（擅长替换/重绘、不擅长等比缩放） | 需要对已生成图做局部修改时 |
| `references/providers/<厂商>.md` | 厂商档案：文档位置、认证、端点、模型表、size 规则、响应格式、已知问题、特有参数 | 下单前必读当前厂商档案 |
| `references/profile.example.md` | 工程档案中性示例（默认值 / 画风 / 负向词 / 决策来源 / 解释器） | 建工程档案 `.image-generation/profile.md` 时 |

**同目录 `scripts/` 五件套**：

| 脚本 | 用途 | 何时跑 |
|---|---|---|
| `generate.py` | 下单出图（generations / edits，多厂商统一入口）。**落盘格式跟 `--out` 扩展名：`.png` 才出 PNG，其余（含无扩展名）写 JPEG（默认 q95，`--jpeg-quality` 可调；带 alpha 的源回退写 PNG）** | 工作流程第 4 步 |
| `mask_editor.py` | 浏览器里画重绘蒙版：**多选区可叠加**（矩形/椭圆/**多边形**/画笔/橡皮都是独立选区，右侧列表可点选、单独删除，`Ctrl+Z` 逐步撤销；多边形单击落点、双击闭合、Backspace 退点、Esc 放弃）、比例锁（1:1 / 4:3 / 3:2 / 16:9 / 21:9）、拖手柄改尺寸、拖框内移动、数值输入、方向键微调（框 / 手柄双目标）、缩放平移 | 需要 mask 局部重绘，或要框一个区域取坐标时 |
| `bbox_from_mask.py` | 蒙版 PNG → 归一化 `0–999` 坐标 | 画完蒙版要写进 Seedream 坐标编辑时 |
| `compress_refs.py` | 把参考图压到 base64 上传预算（默认 6MB），压完再 `--image` 传 | 走 JSON base64 通道（apiyi / seedream）且参考图体积偏大时 |
| `convert_assets_to_jpg.py` | 图片库批量转高质量 JPEG（`--dry-run` / `--delete-originals` / 自动重指软链接） | 库里攒了非 JPG 图想统一瘦身时 |

**改了 `scripts/` 或 `tests/` 之后先跑测试**：`"<PYTHON>" "<SKILL_ROOT>/tests/run_e2e.py"` —— 先跑**离线单测**（零网络零费用；完整清单见 `tests/README.md`），再跑**无头 Chromium** 的交互断言 + 蒙版像素校验；`--unit-only` 只跑离线那半，验"测试真的能失败"用 `"<PYTHON>" "<SKILL_ROOT>/tests/mutation_check.py"`；浏览器半场首次需 `cd "<SKILL_ROOT>/tests" && npm install && npx playwright install chromium`。

## 未覆盖功能与新增厂商

**新功能**（新参数/新端点/新模型行为）：查当前厂商档案「文档位置」节（帮助中心 URL + `/v1/models` 自描述 + 非法参数探针不计费）→ 结论**回写该厂商档案** → 能固化成逻辑的回写 `generate.py` → 再执行。

**新厂商**三步：
1. 复制 `references/providers/_template.md` 新建 `references/providers/<厂商>.md`（固定小节：文档位置 / 认证与端点 / 参数白名单 / 模型表 / **size 规则与官方常用档** / 响应格式 / 扣费 / 已知问题 / 特有参数；`Error Reference` 为可选节）；
2. 在 `generate.py` 的 `PROVIDERS` 注册表加条目（base、env_key、端点路径、edit_format、response、size_rules、**common_sizes 官方常用档**）；size 规则不同则在 `SIZE_RULES` 加规则集；**同一网关上的模型族契约不同时**（size 规则 / 是否支持 `quality` / 参考图传递方式 / 特有参数）**不新开 provider**，改在该 provider 的 `models: {<model>: {...}}` 覆盖表登记（`resolve_provider` 负责合并；如 `infistar` 下的 `doubao-seedream-5-0-260128`）；
3. 用该厂商最小参数单（1K 单图）验证一次——**同样先列参数表获用户确认**，把实测写回档案。

**跨厂商铁律**：未建档厂商 / 未定义 size 规则 → 拒绝下单，先建档；分辨率不合规与计费确认见「工作流程」第 3 步与核心规则 1。

## 核心规则

1. **确认门不可跳过（每单一次）**：生图计费，**任何一单**（含用户已说「再来一次/迭代一次」的方向指令）都必须先列出**该单完整参数**（模型/分辨率/参考图/蒙版状态/输出路径/提示词全文）并获得明确确认，确认=接受本单计费；方向指令 ≠ 参数确认，禁止沿用上单参数直接下单。
2. **参数全量平铺**：每次都列全量（含厂商特有字段与档位换算结果），不用选项控件。
3. **不自动改规格**：分辨率/参数不合规只报错与推荐，替换权在用户。
4. **size 禁用 `auto`**：每单必须给**确定的像素值**（参数表写明解析后的 `WIDTHxHEIGHT`，如 `1792x1008`）；`auto` 已实测输出 1:1 方图，脚本层硬拒绝。
5. **如实回报**：实际分辨率、核对偏差必须报告。
6. **花费意识**：默认 size 取工程档案 `.image-generation/profile.md` 的 `default_size`（无档案或未配置则不设默认）；分辨率/张数越高越贵，**一律不得擅自升档**——包括"为了更清晰""为了补细节""底图更大"这类看起来合理的理由，**都必须先向用户单独提出并获同意**。**禁止批量测试**。
7. **比例/几何修正走 mask 局部编辑**：纯文字比例锁已 0/9 失效——修比例用 `--mask` 圈区 + 几何指令，**渐进迭代**（每轮重复不变量+禁止回弹）；`edits` 的 `size` 必须显式匹配输入画幅（`auto` → 1:1 方图，已实测）。
8. **坐标框选编辑（Seedream）+ 多选区蒙版**：`mask_editor.py` 支持多选区（矩形/椭圆/多边形/画笔/橡皮，可点选/单删/多步撤销，导出为黑白位图并集，下游 `--mask`/`bbox_from_mask.py` 无感）——能力清单见 `scripts/` 表与 `references/coordinate-edit.md`。对已生成图做局部修改：矩形框选 + `bbox_from_mask.py` 取归一化坐标，把 `Image N x1 y1 x2 y2` 写进 prompt。**擅长"区域内替换/重绘"，不擅长"精确等比缩放"**（要精确缩放走合成法）。
9. **独立任务原则（提示词禁引生成历史）**：生图模型没有上下文，提示词里**禁止任何引用先前生成的措辞**（"在此基础上""再缩小一些""上次那版"…），也不写"生成一张…/以图X为依据"这类生成行为叙述——只描述**本单输入图**里"现在是什么样 → 要改成什么样"。详见 `references/prompt-checklist.md`「两条提示词纪律」。
10. **输出命名**：按工程档案 `.image-generation/profile.md` 的 `output_naming` 生成 `--out`；无档案或未配置时建议时间戳前缀写成 `YYYYMMDD-HHMMSS-<简短说明>.jpg`（如 `20260929-143012-move-01.jpg`），**文件名排序即可定位最新一单**。下单前用当前时间生成前缀，不要沿用上单文件名。
11. **编辑一律优先用 `--mask`**：凡是"改局部、保其余"的编辑（尤其**连续多轮迭代**），必须优先使用 `--mask`——**普通 edits 是整幅重绘，多轮会让背景逐轮劣化**（已实测）。mask 的"透明区=重绘、不透明区=像素级保留"是**背景不被过水的唯一手段**。用户已明确此后编辑尽量加 mask。
12. **画风段按场景判定**：**从零生图 / 重绘式放大（高清化）/ 换姿态换外观 / 多图合成**这四类**必写**画风段；纯蒙版局部重绘与轻微编辑可省（底图自带画风）。画风段只写**渲染语言 + 光照与饱和度基调 + 负向**，**不写材质**（随素材变化，写进各自提示词）、**不做统一色卡**（颜色以参考图为准）。模板与判定表见 `references/prompt-checklist.md` 第 5 段。
