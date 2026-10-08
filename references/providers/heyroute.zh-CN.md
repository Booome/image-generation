# 厂商档案 · HeyRoute

> 单厂商档案固定小节：文档位置 / 认证与端点 / 参数白名单 / 模型表 / size 规则 / 响应协议 / 扣费 / 已知问题 / 特有参数。
> 新增厂商复制本结构为 `references/providers/<厂商>.md`，并在 `scripts/generate.py` 的 `PROVIDERS` 注册。

## 文档位置

- **官方 skill 仓库（权威协议参考）**：`https://github.com/heyroute-ai/skills` —— 仓库内 `image-gen/SKILL.md` + `image-gen/scripts/heyroute_image.py`（零依赖参考实现）+ `image-gen/references/prompting.md`（提示词方法论）。**这些是上游仓库里的文件，本 skill 目录下并不存在。** 遇未覆盖功能**先读这里**。
- 帮助中心：`https://heyroute.ai/help`（SPA，需浏览器渲染）
- API 自描述（带 Bearer）：`GET /v1/models`
- 非法参数探针：SSE 前的参数错误会返回普通 JSON 400 并附完整规则（**不计费**）；但注意**宽松参数可能直接开始生成并计费**——只对已知会被拒的字段（如 size 格式）用探针。
- Base：`https://heyroute.ai/v1`（OpenAI 兼容）

## 认证与端点

- 认证：`Authorization: Bearer $HEYROUTE_API_KEY`；另建议带 `Accept: text/event-stream`
- `POST /v1/images/generations` — JSON，文生图
- `POST /v1/images/edits` — `multipart/form-data`，改图/参考图；`image` 为文件字段，**多图重复同名 `image` 字段**（第一张为主体图）；可选 `mask` PNG 蒙版

## 参数白名单（传别的会被 400 或被忽略）

| 参数 | 取值 | 说明 |
|---|---|---|
| `model` | `gpt-image-2`（官方 skill 只此一个）；另见下方模型表 | **已实测**：`gpt-image-2`、`nano-banana-pro`、`gemini-3-pro-image`；其余 id 见下方模型表，未实测者用前先探 |
| `prompt` | 文本 | 必填 |
| `n` | `1` | **只支持 1 张** |
| `size` | `auto` 或 `宽x高` | 见下方 size 规则 |
| `quality` | `low` / `medium` / `high` / `auto` | **必须传，默认 high**（本 skill 默认 high） |
| `stream` | `true` | 协议声明，固定传 |

**不要传**：`response_format`、`background`、`output_format`、`style` 等（被忽略/过滤，结果恒为 b64）。

## 模型表（以 /v1/models 为准，2026-09-24）

官方 skill 只覆盖 `gpt-image-2`；其余为 /v1/models 实测列出（`owned_by` 均显示 openai）。**除已标注实测者外，用前先查官方 skill 或探针**：

| 模型 | 状态 |
|---|---|
| `gpt-image-2` | 官方 skill 覆盖；上游原生上限 ~1.57MP（见已知问题） |
| `gpt-image-2.5` | 未验证 |
| `nano-banana-pro` | **已实测**（= Google Gemini 3 Pro Image）——参考图遵循最佳，但分辨率仅 1K；见下方专节 |
| `gemini-3-pro-image` | **已实测（2026-09-28）**：`/images/edits` 可用；`size=16:9 4K`（`3840x2160`）→ **实出 `1376x768`**，与 `nano-banana-pro` 同款 1K 行为（size 只定宽高比） |
| `nano-banana-2` | 未验证（推测 = Gemini 3.1 Flash Image） |
| `gemini-3.1-flash-image` | 未验证 |
| `flux-klein-2` | 未验证 |
| `grok-imagine-image` | 未验证 |

### Gemini 图像系（nano-banana-pro = Gemini 3 Pro Image）

> 2026-09-24 建档（第 11 单实测 + Google 官方文档）。heyroute 侧 id：`nano-banana-pro`、`gemini-3-pro-image`、`nano-banana-2`、`gemini-3.1-flash-image`。

**官方规格（Google，`ai.google.dev` / Vertex）**
- 分辨率：**1K / 2K / 4K**（4K 标 Preview）；**原生参数是 `aspectRatio` + `imageSize`（`"1K"/"2K"/"4K"`），不是 `WIDTHxHEIGHT`**
- 宽高比：1:1、3:2、2:3、3:4、4:3、4:5、5:4、9:16、**16:9**、21:9（部分平台另有 1:4/4:1/1:8/8:1）
- 参考图：最多 14 张（高保真 6 张）
- 输出 token：1K/2K→1120、4K→2000（按像素计费）；输入每张 560 token

**heyroute 实测（`nano-banana-pro`，2026-09-24）**
- 调用：`POST /v1/images/edits`（multipart 多图重复 `image` 字段）+ `size: "3840x2160"` + `quality: "high"` + `stream: true`——**`quality`/`size` 均未被拒**（无 400）。
- **参考图生效且遵循度目前最佳**：门出成**矩形双扇+百叶通风口**（同参考）、兽为尖刺暗红巨兽（同参考）、兽巢含钢筋/头骨/**蜂窝金属残片**。
- **分辨率只有 1K**：请求 `3840x2160`（8.29MP）→ **实出 `1376x768`（1.06MP，16:9）**。即 heyroute 的 `size` 对 Gemini 系**只用来定宽高比，`imageSize` 默认落到 1K、像素数被忽略**。
- **未知**：如何请求 2K/4K——OpenAI 的 `size` 字段无 `imageSize` 位；heyroute 是否暴露可设 imageSize 的参数（名字未知）**无文档**。放宽尺寸探针**会直接计费**（宽松模型），不能免费试。

**结论**：要「参考图一致」选 Gemini 系；要「4K」此路暂不通（需先摸到 heyroute 的 imageSize 参数）。

## size 规则（`size_rules: pixel_window`，400 报错原文实测）

`auto` 或 `宽x高`：双边 16 倍数、最长边 ≤ 3840、比例 ≤ 3:1、总像素 ∈ [655360, 8294400]。
> 上行为**上游网关的规则**（客观记录）。**本地不再据此校验**：2026-09-29 起全 provider 删除边长倍数校验，`WIDTHxHEIGHT` 只查长边/比例/像素窗，奇数边长原样交给 API 判断。
常用档（官方 skill）：`1024x1024`（最快）/ `2048x2048` / `2880x2880`（最大方图）/ `1536x1024` / `1024x1536` / **`3840x2160`（4K 横）**。

### 口语档位换算（短边 = 1024×K，精确比例，上限钳制；`resolve_size()` 实现）

| 档位 | 换算 |
|---|---|
| 3:2 1K | 1536x1024 |
| 3:2 2K | 3072x2048 |
| 3:2 4K | 3504x2336（钳制；**未验证出图是否真 4K，见已知问题**） |
| 16:9 1K | 1792x1008 |
| 16:9 4K | 3840x2160（官方常用 4K 横档） |

参考：infinite-canvas 项目的 3:2 4K 档为 `3520x2336`（16 倍数合法，比例 1.507）。

## 响应协议（`response: sse`，与 OpenAI 官方不同）

- **固定 SSE**：HTTP 200 + `text/event-stream`，无论是否传 stream；**不要用 OpenAI SDK 的同步 JSON 方法**
- 事件序列：`started → heartbeat（每 15s）→ completed | error → done → 断开`；生成一般 30–120s
- 成功图在 **`completed` 事件 `data[0].b64_json`**（PNG base64）
- **HTTP 200 不代表成功**：业务错误在 `error` 事件（费用自动退回）；仅 SSE 前的鉴权/余额/参数错误才是普通 JSON 4xx
- 保存后**读图片元数据验收实际像素**（实际尺寸以返回为准）

## 扣费规则

- 生成失败（error 事件 / 预扣失败）**自动退回**
- **生成成功后中途断开仍扣费**——必须读完流再退出
- 402 = 余额不足；429 按 `Retry-After` 等待

## 错误对照（官方 skill）

| 现象 | 含义 | 处置 |
|---|---|---|
| HTTP 401 | 令牌无效/未带 | 检查 HEYROUTE_API_KEY |
| HTTP 402 `insufficient_user_quota` | 余额不足 | 提示充值 |
| HTTP 403 | 分组未开放模型/令牌白名单 | 检查令牌分组 |
| HTTP 400 参数类 | size/n/quality 不合规（size 报错附完整规则） | 按白名单改 |
| HTTP 400 `wrong_image_api_path` | Base URL 少 `/v1` | 按 `correct_url` 修 |
| HTTP 429 | 限流/冷却 | 按 Retry-After 等 |
| SSE `error` | 生成失败（上游/内容策略） | 展示 message；**已退费** |

## 已知问题

- **[PENDING] 高分辨率档实测模式（2026-09-23，gpt-image-2 + quality=high + stream）**：
  | 请求 size | 结果 | 耗时 |
  |---|---|---|
  | `3504x2336`（3:2 4K 换算） | 降级实返 1536x1024（两次） | ~40s |
  | `3520x2336` | 连接层挂起（未扣费，服务端未开始） | — |
  | `3840x2160`（首次） | 连接层挂起（未扣费） | — |
  | **`3840x2160`（连接修复后重试）** | **实返 `1672x941`**（16:9 比例正确、非 16 倍数、**总像素 1.573MP ≈ 1536x1024 同预算**） | ~40s |
  | `1536x1024`（1K 3:2） | 成功 | ~40s |
  **根因（实证）**：**上游 gpt-image-2 固定按 ~1.57MP（1536x1024 级）像素预算生成，请求 size 只决定宽高比、不提升像素**——`3840x2160`→1672x941（16:9 同像素）与 `3:2`→1536x1024 互为铁证。**原生 4K 此路不通（已实证）**；网关的 16 倍数/3840 规则只是入参校验，不代表上游出图尺寸。
  **连接快速失败三层**（generate.py，源自官方 skill：心跳 15s、官方脚本 timeout 120）：
  ① preflight `GET /models`（8s/15s，零费）；② POST `timeout=(8, 60)`；③ 流总 cap 240s（`--timeout`）。三层验证有效：连接问题 8–60s 内暴露。
  **可行路线（用户拍板）**：heyroute/gpt-image-2 按其**原生上限 ~1.57MP（3:2 = 1536x1024）**出图；**不使用插值放大**；原生 4K 等**后期新增支持 4K 的 provider**（届时走 skill 新增厂商三步建档）；或换 heyroute 其他模型（未验证，下单前必须用户确认）。
  （旧假设「缺 quality/stream」已于 2026-09-23 补参后证伪。）
- **[已闭环] 探针风险**：对宽松模型（nano-banana/flux/gemini）发非法 size **不会被拒、直接开始生成计费**——探针只允许用于 gpt-image-2 的 size 类参数。

## 特有参数

- `mask`（edits 可选 PNG 蒙版，**已实现 `--mask` 并实测**）：透明区=重绘、不透明区=像素级保留。
  **实测结论（确定）**：① `edits` 的 `size` **必须显式匹配输入画幅**（如 `16:9 1K`），传 `auto` 上游回落 1:1 **方图输出**；② mask+edits 是**比例/几何修正的可行路径**——几何缩放指令在该模式下首次起效（对比纯文字锁 0/9 完全失效），蒙版外不变量执行良好、区内补全自然；③ 单轮缩放幅度可能执行不足 → **渐进迭代**（每轮提示词重复不变量 + 「在已缩基础上继续缩、禁止回弹」）。
