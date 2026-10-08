# 厂商档案 · APIYi（Seedream 渠道）

> 单厂商档案固定小节：文档位置 / 认证与端点 / 参数白名单 / 模型表 / size 规则 / 响应协议 / 扣费 / 已知问题 / 特有参数。
> 建档（2026-09-25）：来源＝官方文档（docs.apiyi.com）+ `GET /v1/models` 实测；**尚未**经真实出图验证。

## 文档位置

- 官方文档（**权威**）：
  - `https://docs.apiyi.com/api-capabilities/seedream-image/overview`（总览 / 定价 / 技术规格）
  - `.../seedream-image/text-to-image`、`.../seedream-image/image-edit`（代码示例 / 参数速查）
  - `.../image-api-best-practices`（timeout / 计费口径 / base64 处理）
  - 任意文档页地址后加 `.md` 得纯文本版；索引 `https://docs.apiyi.com/llms.txt`
- API 自描述（带 Bearer）：`GET /v1/models` —— 实测 HTTP 200、291 个模型，含 `seedream-5-0-260128`（另有 5-0-flash / 5-0-pro / 4-5 / 4-0）
- Base：`https://api.apiyi.com/v1`（备用域名 `https://vip.apiyi.com/v1`）

## 认证与端点

- 认证：`Authorization: Bearer $APIYI_API_KEY`
- **仅一个端点**：`POST /v1/images/generations` —— 文生图 / 单图编辑 / 多图融合 / 批量序列**全靠请求体参数切换**
- **没有 `/v1/images/edits`，也没有 `mask`**（与 OpenAI gpt-image-2 的 multipart 编辑路径完全不同）

## 参数白名单

| 参数 | 取值 | 说明 |
|---|---|---|
| `model` | `seedream-5-0-260128`（= 5.0-lite）等 | 必填 |
| `prompt` | 文本 | 必填；官方建议 ≤300 汉字 / 600 英文词；多图场景用「图1/图2」指代顺序 |
| `image` | 字符串数组 | **参考图**：元素为 URL 或 `data:image/<小写格式>;base64,...`；**最多 10 张**；输入参考图 + 输出图 ≤ 15 |
| `sequential_image_generation` | `disabled` / `auto` | 单图输出用 `disabled`；5.0-pro / 5.0-flash **不可传**（传任何值即 400） |
| `sequential_image_generation_options.max_images` | 1–15 | 仅 `auto` 模式生效 |
| `size` | 档位或 `WxH` | 见下 |
| `response_format` | `url` / `b64_json` | 默认 `url`（Seedream 原厂默认即 URL） |
| `output_format` | `png` / `jpeg` | 5.0 系支持 png；4.5 / 4.0 仅 jpeg |
| `watermark` | 布尔 | **须显式 `false`**（默认随版本 / 分组变化） |
| `stream` | 布尔 | 5.0-lite 支持；5.0-pro / 5.0-flash 传入即 400 |

**不发**：`quality`（该模型不支持，传即 422/400）、`n`（被静默忽略，恒 1 张）、`seed`（4.x / 5.x 不生效）。

## 模型表（/v1/models 实测）

| model | 说明 | 价格 |
|---|---|---|
| `seedream-5-0-260128` | 5.0-lite（本渠道默认；png/jpeg、组图、流式） | $0.035/张 |
| `seedream-5-0-flash-260915` | 快速版（参考图不收费） | $0.018/次 |
| `seedream-5-0-pro-260628` | 专业版（约 2 分钟/张，无组图 / 流式） | $0.12/次 |
| `seedream-4-5-251128` | 4K + 强文字渲染（仅 jpeg） | $0.04/张 |
| `seedream-4-0-250828` | 最便宜的 4K（仅 jpeg） | $0.03/张 |

## size 规则（`size_rules: seedream_lite_px`）

- **档位**：`2K` / `3K`（5.0-lite —— `seedream-5-0-260128` **无 4K**）；4.5 / 4.0 才有 `4K`。
- **精确像素**（5.0-lite）：总像素 ≈ [2560×1440, 3072×3072×1.1025 ≈ 10.4MP]，宽高比 [1/16, 16]，**无 16 倍数限制**。
- 本 skill 采用保守上限 `max_px = 10404496`；常用值：16:9 = **4096×2304**、3:2 = **3744×2496**、1:1 = **3072×3072**。
- ⚠ 上限口径冲突见「已知问题」。

## 响应协议（`response: json`）

- OpenAI 标准**同步** JSON：`{"data":[{"url": ...}], "usage": {...}}`；`url` 是 BytePlus TOS 临时链接（**约 24h 失效**，须立即转存），或 `b64_json`（纯 base64，无 `data:` 前缀）。
- 无任务 ID；客户端断连结果丢失**但仍计费** → timeout 必须留足（Seedream 建议 60s 起，4K+hd 约 30–60s）。

## 扣费规则

- 按 `usage.generated_images` 实际张数计费；**参考图不额外计费**。
- **不计费**：400 / 403（内容审核）/ 429 / 503。**仍计费**：客户端超时主动断开。
- `n` 不生效；多张须走 `sequential_image_generation: "auto"`（按实际张数计费）。

## 已知问题

- **参考图优先传公网 URL**：官方强烈建议（BytePlus 直接从新加坡下载，请求体仅几 KB）。base64 需跨境上传，20–30MB 会撞原厂 600s 请求体超时 → `400 Error when parsing request`，**且失败后不会自动回退 URL**。只能 base64 时：长边 ≤2048、q0.9 重编码、多张合计 ≤6MB —— 这套处方已固化成 **`scripts/compress_refs.py`**（默认 `--max-edge 2048 --quality 90 --target-bytes 6MB`），压完把输出路径喂给 `--image`。
- **5.0-lite 精确像素上限口径冲突**：官方「精确像素」通用段写 [1280×720, 4096×4096]，overview 的 Warning 又称「5.0 系下限更高、上限更低」（5.0-lite 下限 ≈2560×1440）。本档案取火山 3K 上限 ~10.4MP 作保守边界。
- **`n` 静默忽略**：恒返回 1 张（按 1 张计费）。
- **URL 约 24h 失效**：必须服务端立即下载转存。
- **未验证**：本渠道尚未经真实出图；参考图走 `image` 数组的端到端行为待首次实测确认。

## 特有参数

- `image`（参考图数组，URL 或 base64 data URI）—— 与 infistar 的关键差异：字段名是**单数 `image`**（infistar 网关用复数 `images`），`generate.py` 以 `ref_field` 区分。
- `max_refs: 10` / `warn_ref_bytes: 6MB` / `max_ref_bytes: 20MB`：`generate.py` 发送前校验——**超 10 张硬拒**（网关 `maxItems: 10`，错误码表明确 400）；base64 合计 **>6MB 仅警告**（官方压缩建议值，**非**错误码条件）、**>20MB 硬拒**（文档明确的"不要传 20MB 以上请求体"超时红线）。
- `layer_decomposition`（仅 5.0-flash：单图 → 背景底图 + 多张 RGBA 透明图层，按输出张数计费）。
