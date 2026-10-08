# 变更需求单 · image-generation（2026-10-09）

> **本文件是临时实施指令，不入库、不进版本控制**；实施完成后请删除。
> 基线：`HEAD = ba6af47` **加上**当前工作区未提交改动（`--proxy` / SKILL.md §7 / profile `proxy:` 已实现，见第 0 节）。
> 每条给出「现状 → 要求 → 验收」，可独立实施、独立验收。行号以本单起草时的文件为准。

---

## 0. 基线核对（先读，避免重做已完成项）

**已落地，请勿重做**：

| 项 | 落点 |
|---|---|
| A1 密钥三级来源 | `scripts/generate.py` `read_env()` / `_read_keys_file()`（`a59f70f`） |
| A3 超时对齐 | `SKILL.md` 宿主适配第 6 条 |
| A4 mask 编辑器 URL 始终打印 | `scripts/mask_editor.py` |
| A7 profile 不加载 | `SKILL.md` 宿主适配第 5 条 |
| A12 显式代理 | `generate.py` `--proxy` / `$IMAGE_GENERATION_PROXY` / 档案 `proxy:`（**未提交**） |
| 沙箱代理规则 | `SKILL.md` 宿主适配第 7 条（**未提交**） |
| `proxy:` 字段登记 | `references/profile.example.md` + zh-CN（**未提交**） |

**本单要做的**：R1（删除护栏）· R2（覆盖护栏）· R3（BOM）· R4（凭据脱敏）· R5（测试）· R6（可选）· R7（文档）。

---

## R1 · P1 · `--delete-originals` 必须显式二次确认

**现状**：`scripts/convert_assets_to_jpg.py:83-88`

```python
if args.delete_originals and not args.dry_run:
    removed = 0
    for path, _, _, _, _ in converted:
        path.unlink()
        removed += 1
    print("deleted %d originals" % removed)
```

三个问题：① 无确认门，一次误传参即**永久删除**原图（不经回收站）；② 循环内无 `try/except`，Windows 上任何一个文件被占用/只读就抛 traceback 中断，**前面已删的无法回滚**，且剩下的静默不删；③ 无审计记录，事后无法知道删了哪些。

**要求**：

1. `--delete-originals` 单独出现即 `die`（非零退出、**在任何删除之前**），错误信息里给出可直接复制的完整命令（补上 `--yes`）。
2. 新增 `--yes`；仅当 `--delete-originals --yes` 同时出现才执行删除。
3. 删除前先把清单写到 stdout（相对路径 + 字节数 + 合计），并**落盘** `<root>/deleted-originals.txt`（追加一次带时间戳的头，记录每行：时间 · 路径 · 字节数）。该清单文件本身不参与 `SRC_EXT` 扫描（后缀 `.txt`，天然排除）。
4. 逐个文件 `try/except OSError`：失败者记入 `failed` 列表、**继续处理其余文件**；末尾汇总 `deleted N, failed M` 并逐条打印失败原因；`M > 0` 时退出码为 1。
5. `--dry-run` 语义不变：不删任何文件，也不写清单，仅在 stdout 预览。
6. 脚本顶部 docstring 的 Usage 行同步加上 `--yes`。

**验收**：

- `--root X --delete-originals`（无 `--yes`）→ 非零退出、**磁盘上零变化**、stderr 指明缺 `--yes`。
- `--root X --delete-originals --yes --dry-run` → 仍零变化。
- 正常路径 → 清单文件存在，行数与 `deleted` 数一致。
- 构造一个只读/被占用文件 → 其余文件删完、退出码 1、汇总里列出该文件及其原因。

---

## R2 · P1 · 同名 `.jpg` 覆盖保护（与 R1 配套，二者叠加才是完整的数据丢失面）

**现状**：`convert_assets_to_jpg.py:58-64`

```python
dst = path.with_suffix(".jpg")
...
rgb.save(dst, "JPEG", ...)
```

**无条件覆盖**已存在的同名 `.jpg`。而第 5-6 行注释声称 "a sibling .jpg already holding the same pixels (same stem) is overwritten" —— 代码从未验证 "same pixels"。后果：若目录里原本就有一个与 `a.png` 无关的 `a.jpg`，它会被静默销毁；再叠加 `--delete-originals`，则**源与旧目标同时消失**。`--dry-run` 的输出也区分不出「新建」还是「覆盖」。

**要求**：

1. 输出逐行标注 `NEW` / `OVER`（覆盖）/ `SKIP`，并在汇总行分列 `new` / `overwrite` / `skipped` 三个计数。
2. 对**已存在、且 mtime 早于源文件**的 `.jpg`（启发式：不是本次转换的产物），默认跳过并计入 `skipped`；只有显式传 `--overwrite` 才覆盖。
3. 在 docstring 里写明该启发式的局限（例如源图 mtime 被同步工具刷新、或旧 `.jpg` 本就是这个 `.png` 的上一次产物），让跳过成为"可解释的保守行为"而非黑盒。
4. 第 5-6 行的 "same pixels" 注释必须改成与实现一致的描述。

**验收**：

- 目录内造 `a.png` + 同名 `a.jpg`（把 `a.jpg` 的 mtime 设成早于 `a.png`）→ 默认运行后 `a.jpg` 字节不变、计数进 `skipped`；加 `--overwrite` 后被替换、计数进 `overwrite`。
- 无同名旧文件时，行为与当前版本一致（`NEW`）。

---

## R3 · P1 · 读 `keys.env` 与 `profile.md` 必须兼容 BOM

**现状**：`generate.py:245`（`_read_keys_file`）与 `generate.py:294`（`_profile_frontmatter`）都用 `read_text(encoding="utf-8")`。

**问题**：Windows PowerShell 5.1 的 `Out-File -Encoding utf8` / `Set-Content -Encoding utf8` 会写入 UTF-8 BOM（`EF BB BF`）。带 BOM 时：

- keys 文件首行的 key 实际是 `\ufeffNAME` → 匹配不到 → **静默视为未配置**（或静默回落到更低优先级来源）；
- profile 文件 `text.startswith("---")` 为假 → **整块 frontmatter 被忽略**，`default_provider` / `python` / `proxy` 全部静默失效。

两者都是**静默失败**，排查成本远高于修复成本。

**要求**：

1. 两处读取改用 `encoding="utf-8-sig"`（对无 BOM 文件无任何副作用）。
2. `_profile_frontmatter` 另加一行兜底：`text = text.lstrip("\ufeff")` 后再判 `startswith("---")`。
3. 其余解析逻辑不动。

**验收**：新增回归用例（见 R5 第 6 条）——带 BOM 的 `keys.env` 与 `profile.md`，断言结果与非 BOM 时**逐字段相同**。

---

## R4 · P2 · 代理 URL 打印前脱敏

**现状**：`generate.py:739-740` → `print(f"proxy: {proxy}", file=sys.stderr)`

**问题**：代理 URL 允许带凭据（`http://user:pass@host:port`）。这一行会把凭据写进终端、被重定向的文件，以及宿主日志（WorkBuddy 的沙箱日志会逐条记录命令的 stdout/stderr）。

**要求**：

1. 新增 `mask_proxy(url)`：若含 userinfo 则替换为 `http://***:***@host:port`（保留 scheme/host/port 便于排查），无 userinfo 时原样返回。
2. 打印改为 `proxy: <masked>`。
3. 顺带回显来源，便于排查"为什么没走代理"：`proxy: <masked> (from cli|env|profile)`——因为目前命令行传入与档案读取的打印完全相同，无法区分。

**验收**：单测 `mask_proxy("http://u:p@127.0.0.1:20171")` 输出不含 `u` / `p` 原文；`mask_proxy("http://127.0.0.1:20171")` 原样返回。

---

## R5 · P2 · 为本次新增逻辑补离线单测

**现状**：`tests/` 对 `read_env` / `_read_keys_file` / `_profile_frontmatter` / `resolve_proxy` **零覆盖**（唯一相关处是 `tests/test_request.py:61` 的 `gen.read_env = lambda name: "test-key"` 打桩）。

**要求**：新增 `tests/test_env.py`，并加入 `tests/run_e2e.py:51-52` 的 unit 元组。

硬约束：

- **完全离线**（不发任何网络请求）；
- **不读机器真实注册表、不读真实密钥**；
- **不打印任何密钥值**（沿用 `test_generate.py` 的 `check(name, cond, detail)` 风格即可）；
- 用例之间互不污染（用 `tmp_path`/`tempfile` + `monkeypatch`，并在结尾恢复 CWD 与相关环境变量）。

用例至少覆盖：

1. `read_env` 优先级：进程环境 > 注册表 > keys 文件；**空字符串不遮蔽下层**（`os.environ[name] = ""` 时必须继续下探）。
2. `read_env` 在非 win32 时不尝试注册表（monkeypatch `sys.platform` / `winreg`，保证跨平台确定性）。
3. keys 文件：默认相对路径 `.image-generation/keys.env`（chdir 到临时目录验证）；`IMAGE_GENERATION_KEYS_FILE` 覆盖；`#` 注释与空行；单/双引号去引；无 `=` 的行；**值内含 `=` 时保留其余部分**；key 不存在返回 `""`；文件缺失返回 `""`。
4. `_profile_frontmatter`：正常 frontmatter；文件缺失；无 frontmatter；**未闭合 frontmatter**；**值含 `:`**（`proxy: http://127.0.0.1:20171` 必须完整取到）；引号去引；`IMAGE_GENERATION_PROFILE` 覆盖。
5. `resolve_proxy` 优先级：CLI > `$IMAGE_GENERATION_PROXY` > 档案 `proxy:` > `None`；**空串的处理要显式断言并写进 docstring**。
6. BOM 回归（R3）：带 BOM 的 `keys.env` 与 `profile.md` 结果与非 BOM 一致。

**验收**：`python tests/run_e2e.py --unit-only` 全绿、`fails=0`；**并且**：把 R3 的 `utf-8-sig` 改回 `utf-8` 后，新用例必须变红（证明测试真的在守门，而非恒真——与本仓库既有守门器思路一致）。

---

## R6 · P3（可选，请 OpenCode 给判断）· `keys.env` 支持可选 `export ` 前缀

**理由**：用户极易从 shell 脚本或文档里复制 `export FOO=bar` 一行过来，当前实现（`line.partition("=")` 后比较 `k.strip() == name`）会**静默不匹配**，表现为"我明明配了却没生效"。

**要求（二选一）**：

- **支持**：比较前先 `re.sub(r"^export\s+", "", line)`，并加一条用例；
- **不支持**：在 `_read_keys_file` docstring 与 `SKILL.md` 宿主适配第 5 条里把「`export` 前缀不被识别」写成**显式警告**，别让它是隐式陷阱。

---

## R7 · P2 · 文档补充与一个待确认项

1. `references/profile.example.md` 与 `references/profile.example.zh-CN.md` 的 `proxy:` 旁注明：**不要写带用户名/密码的代理 URL**——档案位于工程侧、随工程入库，凭据会一并被提交。凭据类代理请走 `$IMAGE_GENERATION_PROXY` 或命令行。`keys.env` 已有的"不要入库"保持不变。
2. `SKILL.md`「项目定制层」的 `proxy` 说明补同一句提醒。
3. **待确认（不必改代码，但要给结论）**：`SKILL.md:13` 的 `allowed-tools: Read, Write, Bash` 是否真被 WorkBuddy / CodeBuddy 识别？本机内置技能都不使用该字段；若被忽略 → 建议删除以免误导，若被识别 → 保持。（此条无法从本机验证。）
4. 若采纳 R2，须同步修正 `convert_assets_to_jpg.py` 开头注释里与实现不符的描述（R2 第 4 点）。

---

## 附：工程侧待办（**不属于本仓库**，仅供提醒）

`make-money` 工程若真的启用 `.image-generation/keys.env`，需在该工程的 `.gitignore` 里加 `.image-generation/keys.env`；`profile.md` 仍应入库（它承载画风与决策来源，是要随工程走的）。
