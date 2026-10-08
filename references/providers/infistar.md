# 厂商档案 · Infistar

> 单厂商档案固定小节：文档位置 / 认证与端点 / 参数白名单 / 模型表 / size 规则 / 响应格式 / 扣费 / 已知问题 / 特有参数。
> 新增厂商复制本结构；本档案为手工建档（2026-09-23），来源=API 实测探针 + 用户成功案例。最近实测更新：**2026-09-28**（`gpt-image-2.5-sunburst` 图片编辑）。

## 文档位置

- **无公开 skill/文档仓库**（与 heyroute 不同）——行为以 API 实测 + 用户成功参数为准；发现官方文档 URL 时补录于此。
- API 自描述（带 Bearer）：`GET /v1/models`（实测 198 个模型，含 `gpt-image-2`）
- 探针（校验层拒绝=不计费）：发非法 `size`（如 `bogus-size`）→ `400 {"message":"size must be auto or WIDTHxHEIGHT","type":"new_api_error"}` —— **只给格式，不给白名单数值**。
- 网关类型：**new-api**（`new_api_error`），完全兼容 OpenAI 协议。

## 认证与端点

- 认证：`Authorization: Bearer $INFINISTAR_API_KEY`
- Base：`https://infistar.cc/v1`
- `POST /v1/images/generations` — JSON，文生图
- `POST /v1/images/edits` — `multipart/form-data`，多图重复 `image` 字段。**已实测可用**（2026-09-28，`gpt-image-2.5-sunburst`，2 图；详见「特有参数 · 图片编辑」）

## 参数白名单（OpenAI 兼容系，逐步实测补录）

| 参数 | 取值 | 状态 |
|---|---|---|
| `model` | `gpt-image-2`（另有 `gpt-image-2.5-sunburst/flare`、qwen-image*、doubao-seedream*、wan2.7-image* 等） | 已确认在 /v1/models |
| `prompt` | 文本 | 必填 |
| `n` | 未知上限 | 保守用 1 |
| `size` | `auto` 或 `WIDTHxHEIGHT`（格式已实测）；**白名单数值未知** | ⚠️ 待定——以用户成功参数为准，见下 |
| `quality` | OpenAI 惯例 `low/medium/high/auto` | `high` 已实测可用（2026-09-28 edits 单）；其余档未试 |

### size 规则（`size_rules: pixel_window`）

- **已实测成功（用户案例，2026-09-23）**：`3520x2336`（= 无限画布 4K 3:2 档 `imageSizePresets["4k"]["3:2"]`）→ **原生输出 3520×2336、8.22MP，分毫不差、未裁剪未缩放**（载体图片）。**原生 4K 在此渠道成立**。
- 该成功值恰好满足 heyroute 同款像素窗（≤3840 / ≤8.29MP）——暂沿用 `pixel_window` 做本地校验（不拦截用户常用值）；**16 倍数不再是本地校验项**（2026-09-29 起全 provider 删除边长倍数校验），白名单是否更宽未知，服务端 400 为准。
- 已实测拒绝：`bogus-size`（格式错，400 不计费）。
- `auto`：**本 skill 全局禁用**（显式像素铁律）。
- 档位换算沿用 `3:2 1K/4K` 等口语格式（`3:2 4K` → 会钳到 pixel_window 上限 3504x2336——**注意：渠道实测可用 3520x2336，比钳制值更优**；出 4K 3:2 时**直接显式写 `3520x2336`**，勿用档位换算）。

## 模型表（2026-09-23 实测，节选图像类）

`gpt-image-2`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare`（`supported_endpoint_types` 三者均只标 `image-generation`）；`step-image-edit-2`（**唯一标注 `image-edit`**）；qwen-image 系、doubao-seedream 系、wan2.7 系、grok-imagine-image、gemini 文本系。

- ⚠️ **`supported_endpoint_types` 标注 ≠ 实际能力**：`gpt-image-2.5-sunburst` 虽只标 `image-generation`，其 `/v1/images/edits` **已实测可用**（2026-09-28）。别凭该字段下"不能编辑"的结论。

## 响应格式（`response: json` — 与 heyroute 关键差异）

- **OpenAI 标准同步 JSON**（预期，`stream` 参数已按协议不发送）：`{"data":[{"b64_json":...}]}` — **非 SSE**（heyroute 才是 SSE）
- **实测备注**：早期请求若带 `stream: true`（OpenAI images 标准无此参数），new-api 会回 **SSE 且为裸 `data:` 帧（无 `event:` 名）**——`read_image_token` 已兼容两种方言（Content-Type 自动分流 + 裸 data 帧解析）
- `generate.py` 已适配：非 SSE 响应直接走 JSON 解析路径

## 扣费规则

- 校验层 400 不计费（实测 size 探针）
- 具体计费/退款政策**未知**（无公开文档）——按通用原则：失败问用户查控制台

## 已知问题

- size 白名单未公开，探针不吐数值——**首单前必须拿到用户成功参数或经用户确认的边界探针**
- ~~`edits` + `gpt-image-2` 是否支持参考图（端点类型只标 image-generation）——未实测；备选 `step-image-edit-2`~~ **已闭环（2026-09-28）**：`gpt-image-2.5-sunburst` 走 `/v1/images/edits` 多图参考**已验证生效**，见「特有参数 · 图片编辑」；`gpt-image-2` 本体仍未实测。
- **edits 分辨率偏差（确定性，2026-09-28）**：`size=1792x1008`（`16:9 1K` 档位换算值）→ **实出 `1672x941`**（总像素约 1.57MP）。与 heyroute `gpt-image-2` 同款行为——**size 只取长宽比、按固定像素预算出图**；要拿到更高分辨率须按实测像素反推入参，别指望档位换算。
- **edits 曾出现非确定性 400（2026-09-28）**：两次中文 `当前模型无法处理输入图像。请检查输入图片是否安全或者已下载，不适合进行图像编辑。`（分别带 3 图、2 图），随后**同格式 2 图成功出图**——原因未定位。**不要凭单次 400 判定该模型不支持编辑**，可重试一次。

## 特有参数

- OpenAI 标准集之外**暂无**额外参数；下方为 gpt-image 系 `edits` 的实测行为。

### 图片编辑（`POST /v1/images/edits`，2026-09-28 实测）

- **可用**：`--provider infistar --model gpt-image-2.5-sunburst` + `edit_format: multipart`（`generate.py` 既有路径，未改代码即可跑通）。
- **传图方式**：多图重复 `image` 字段——第 1 张 = 底图（保持构图/姿态），第 2 张 = 参考图（管外观）；实测 **2 张生效**。
- **参数**：`size=16:9 1K` → `1792x1008`（本地 `pixel_window` 校验通过）、`quality=high`、`n=1`、**不传 `stream`**（与 heyroute 固定 SSE 不同）。
- **效果验证**：底图构图与姿态被保留，参考图的外观特征被写入（幼体按角色设定板换回正确毛色/骨刺造型）——**参考图确实生效，不是纯文生图**。
- **分辨率偏差与非确定性 400 样例**：统一见「已知问题」（此处不重复）。

## Seedream（Volcengine 系，`infistar` 下的模型覆盖条目）

> 同网关同 key；因 size 契约不同、且拒绝 `quality` 参数，在 `generate.py` 的 `infistar` 条目下以 `models: {doubao-seedream-5-0-260128: {...}}` 覆盖（`size_rules: seedream_px`，`edit_format: json_images`，`default_quality: null`，`extra_params: {watermark: false, output_format: png}`）。调用方式：`--provider infistar --model doubao-seedream-5-0-260128`。

- **模型**：`doubao-seedream-5-0-260128` = **Seedream 5.0 lite**（火山引擎原生，infistar 代理至火山方舟）。同族另有 `doubao-seedream-4-0-250828` 等。
- **size（官方）**：两选一——① 关键词 `2k`/`3k`/`4k`（模型按提示词自行定尺寸）；② 显式 `WIDTHxHEIGHT`，总像素 **[2560×1440, 4096×4096]**，宽高比 **[1/16, 16]**。已实测：`3840x2160` → **原生输出 3840×2160**（未裁剪）。
- **quality**：**不支持**——传任意值（含 `high`）均 **422**「该模型不支持此参数」。脚本按 `default_quality: null` 整条省略。
- **watermark（官方）**：**默认 `true`**（右下角加「AI生成」）——必须显式 `false`。已实测：传 `watermark=false` 后输出无水印。
- **output_format**：官方支持 `png`/`jpeg`（仅 5.0 lite）。实测**依路径而异**：`json_images` 路径生效（第 10 单返回 PNG）；multipart `/images/edits` 路径被丢弃（第 09 单仍返回 JPEG）。`generate.py` 的 `image_size` 已同时支持 PNG/JPEG 头解析。
- **参考图：两条路径实测均被丢弃 → 本渠道 seedream 实为纯文生图（text-to-image only）**：
  - multipart `/images/edits`（第 09 单，2026-09-24）：门/兽外观与参考图完全不符。
  - JSON `images` 数组 base64（第 10 单，2026-09-24）：同样完全不符（门仍为拱形、兽为通用四足）。
  - 结论：infistar 的 seedream 条目只声明 `image-generation`，两条参考图路径都未翻译到火山上游。**要参考图一致请换模型/渠道**（如 heyroute 的 `nano-banana-pro`、`gemini-3-pro-image`）。
- **下载**：返回火山 TOS 直链（`ark-acg-cn-beijing.tos-cn-beijing.volces.com`），有效期 24h。**实测 `requests` 直连偶发 SSL `UNEXPECTED_EOF`**，`curl.exe` 重试成功——脚本下载失败时可手动 curl 该链接。
- **提示词长度**：官方建议 ≤300 汉字或 600 英文词；实测 1089 汉字的长提示词仍出图（山体/构图遵循良好），但为稳妥起见，实测采用 354 汉字精简版。
