# image-generation 工具链测试

`python run_e2e.py` 一条命令跑完全部：**离线单测**（多组，零网络零费用）→ **无头 Chromium 交互断言** → **蒙版像素校验 + `bbox_from_mask.py` 集成**。退出码 0 = 全绿。

> 断言清单以各测试文件为准，本文件不写死条数（写死的数字必然随代码漂移）。要验"测试真的会失败"，跑 `python mutation_check.py` —— 它故意改坏实现，要求套件变红。

## 一次性准备

```bash
cd .opencode/skills/image-generation/tests
npm install                        # playwright（node_modules 已被 .gitignore 忽略）
npx playwright install chromium    # 约 115MB，只下载一次
```

## 运行

```bash
python run_e2e.py                              # 默认底图 tests/fixtures/sample.jpg
python run_e2e.py --unit-only                  # 只跑离线单测（不需要 Chromium）
python run_e2e.py --image <path> --keep-mask out.png
```

## 离线单测（多组，不需要 node）

| 文件 | 覆盖 |
|---|---|
| `test_generate.py` | `write_output` 格式契约（`.png` 出 PNG、其余出 JPEG、**已是 JPEG 则不重编码**、带 alpha 回退 PNG、无扩展名补 `.jpg`）、`image_size` 头解析、`detect_format`、`configure_stdio` 尊重显式 env、`_size_ok` 与 `_explicit_errors` 同源 |
| `test_sizes.py` | 7 个档位/显式尺寸 × 4 渠道：比例正确、规则合法、**被上限钳制时必须显式标注**；非法值一律拒绝且给出候选与"未发请求"声明 |
| `test_assets.py` | `compress_refs`：base64 长度、`fit()` 收敛到预算、CLI 报告尺寸**等于写盘尺寸**、预算不可达时非零退出；`convert_assets_to_jpg`：只转该转的、默认保留原图、`--skip`、`--delete-originals`、`--dry-run`、软链接重指 |
| `test_request.py` | 桩掉 `requests.post`：三种请求形态（multipart edits / JSON generations / JSON `image` 数组）的端点、字段、类型、SSE 与 `quality` 的有无 |

## 浏览器 E2E（真实 Chromium）

| 文件 | 作用 |
|---|---|
| `run_e2e.py` | 编排：跑离线单测 → 起服务端（自动选空闲端口）→ 跑浏览器断言 → 校验蒙版 |
| `e2e_server.py` | 无头启动 `mask_editor` 的 HTTP 服务（**把 `webbrowser.open` 换成 no-op，绝不弹出真实窗口**） |
| `e2e.js` | 26 项 playwright 断言 |
| `verify_mask.py` | 保存后蒙版：尺寸、bbox 比例、内外 alpha、覆盖率 + `bbox_from_mask.py` 集成 |

覆盖：绘制 → 比例锁 → 拖角/拖边/拖框内 → 数值输入（H 随比例推导、锁定禁用）→ **输入框聚焦时方向键被吞**（防打字变移框）→ 方向键微调（框 1px / Shift 10px；点手柄后推拉该边）→ Esc 取消手柄 → Ctrl+Z 撤销 → Ctrl+滚轮缩放 / 中键平移 / 适配 → 椭圆同一套比例锁 → 保存 → 蒙版校验。

## 已知边界

- `e2e.js` 的坐标容差按 `1 / view.k` 缩放（屏幕取整会把误差放大到图内像素）。
- Chromium 约 115MB，只在 `ms-playwright` 本机缓存，不随仓库提交。
- 离线单测之间互不依赖，可单独 `python test_xxx.py` 运行。
