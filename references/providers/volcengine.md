# 厂商档案 · 火山方舟（Volcengine Ark）

> 单厂商档案固定小节：文档位置 / 认证与端点 / 参数白名单 / 模型表 / size 规则 / 响应协议 / 扣费 / 已知问题 / 特有参数。
> 建档（2026-09-25）：来源＝官方文档 + `GET /api/v3/models` 实测（135 模型）；已接入并出图验证（见「已知问题」）。

## 文档位置

- 官方文档：`https://www.volcengine.com/docs/82379/1356358`（火山方舟）→ 图片生成 →《Doubao Seedream 5.0 pro 教程》
- API 自描述：`GET /api/v3/models` —— 实测 200、135 个模型，含 `doubao-seedream-5-0-pro-260628`
- Base：`https://ark.cn-beijing.volces.com/api/v3`
- 若本机走 HTTP 代理，需把 `ark.cn-beijing.volces.com` 加进直连名单（`NO_PROXY` / `no_proxy`），否则下载火山 TOS 直链会超时

## 认证与端点

- 认证：`Authorization: Bearer $ARK_API_KEY`
- 端点：`POST /api/v3/images/generations`（OpenAI 兼容；文生图/参考生图统一入口）
- 模型可用**模型 ID**（如 `doubao-seedream-5-0-pro-260628`）或**推理接入点 ID**（`ep-xxxx`）；`/models` 已列出模型 ID，可直接使用

## 参数白名单

| 参数 | 取值 | 说明 |
|---|---|---|
| `model` | `doubao-seedream-5-0-pro-260628` 等 | 必填 |
| `prompt` | 文本 | 必填；≤4000 tokens（中文约 2600 字），建议中文 ≤300 字 |
| `image` | string[] | 参考图：URL 或 `data:image/<小写格式>;base64,...`；**最多 10 张**，单张 ≤30MB |
| `size` | 比例（`16:9` …）或 `WxH` | 像素总范围 `[921600, 4624220]`，比例 `[1/16, 16]` |
| `quality` | `1K` / `1.5K` / `2K` | **是分辨率档位**，不是 low/medium/high → 本 skill 用像素 `size`，**不发此参数** |
| `response_format` | `url` / `b64_json` | 默认 `url`（火山 TOS，约 24h） |
| `watermark` | 布尔 | **默认 `true`，须显式 `false`** |
| `sequential_image_generation` / `stream` / `tools` / `optimize_prompt_options` | — | **5.0 Pro 均不支持**（仅 4.0 / 4.5 / 5.0-lite 支持） |

## 模型表（/models 实测）

`doubao-seedream-5-0-pro-260628`（5.0 Pro：画质优先，1K/1.5K/2K，支持图层拆分/交互编辑）、`doubao-seedream-5-0-260128`（5.0-lite：2K/3K/4K，支持组图/流式）、`doubao-seedream-5-0-flash-260915`、`doubao-seedream-4-5-251128`、`doubao-seedream-4-0-250828`。

## size 规则（`size_rules: seedream_pro_px`）

- 精确像素：总像素 `[921600, 4624220]`、比例 `[1/16, 16]`、**无 16 倍数限制**、边长 >14px
- **本地保护上限 `max_edge = 8192`**（`generate.py` 的 `seedream_pro_px` 自带，**官方口径没有这条**）：仅作护栏，因 `8192² ≫ max_px`，它永远排在像素窗之后触发，实际拦截不到合法尺寸
- 常用 2K 值：1:1 = `2048x2048`、3:2 = `2496x1664`、16:9 = `2816x1584`、21:9 = `3136x1344`
- **口语档位实测（2026-09-28）**：`16:9 1K` → `1824x1026`，**实出与请求逐像素一致**（`size_mismatch: false`）
- **5.0 Pro 无 4K**（最高 2K；4K 只在 5.0-lite / 4.5 / 4.0）

## 响应协议（`response: json`）

- `{"model":…, "created":…, "data":[{"url":…, "size":…}], "usage":{"generated_images":N, ...}}`
- `url` 为火山 TOS 临时链接（约 24h 失效），本脚本拿到后立即下载转存
- 同步调用、无任务 ID

## 扣费规则

- 按生成张数计费；用户持有「Seedream 5.0 pro 轻量创作包」（预付费额度）
- 单张失败 / 参数错误是否计费，以火山控制台账单为准

## 已知问题

- ~~尚未出图验证~~ → **已实测（2026-09-25）**：文生图与"参考图 + `image` 数组"端到端生效；参考图遵循良好（门/兽/兽巢与参考一致）。
- **交互编辑（坐标框选）已实测生效**：机制与写法见 `references/coordinate-edit.md`。要点——坐标**不是 API 字段**，而是写进 prompt 的 `Image N x1 y1 x2 y2`（归一化 0–999）；**擅长"区域内替换/重绘"，不擅长"精确等比缩放"**；配套流程用 `mask_editor.py` 框选 + `bbox_from_mask.py` 反解坐标。
- `quality` 语义与 OpenAI 系不同（分辨率档位），本 skill 已规避（不发 `quality`，用像素 size）
- 5.0 Pro 不支持组图 / 流式 / 联网（仅 5.0-lite 支持）
- 内容审核：字节自家模型，审核口径与 OpenAI/Google 不同（实测未拦截兽题材）

## 特有参数

- `image`（参考图数组，**单数名**）——与 apiyi 的 seedream 条目一致
- `watermark` 默认 `true`，必须显式关闭
