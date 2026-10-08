---
# 全部可选；缺省则使用 SKILL.md 的通用默认
default_provider: heyroute
default_model: gpt-image-2
default_size: "16:9 1K"
output_naming: "assets/scratch/YYYYMMDD-HHMMSS-<slug>.jpg"
# 宿主级配置（仅当裸 `python` 缺 requests+Pillow 时才需要）
# 指向一个装了本 skill 依赖的解释器的绝对路径。
# 优先级：环境变量 IMAGE_GENERATION_PYTHON > 本字段 > 裸 `python`
# 例：python: "C:/Users/<you>/.venvs/imagegen/Scripts/python.exe"
# python: ""
---

# 项目档案示例（中性）
[English](profile.example.md) | **中文**

> 复制本文件到 `<工程根>/.image-generation/profile.md` 后按你的项目填写。
> 本文件只是示例，不代表任何真实项目；技能仓库不包含生效的 profile。

## 画风（风格段模板）

示例（中性，按需替换）：
`电影级写实向渲染，柔和自然光照，中等饱和度，克制写实；无 2D 插画感、无动漫赛璐璐风。`

## 负向词（本项目历史踩坑）

- 比例失调
- 主体过小
- 分格拼贴
- 文字水印
- <在此补充你项目踩过的坑>

## 结构与开合方式（历史事故）

- <如：漏写开合方式，反复生成错误结构——遇可动结构必须显式写运动方式并给反例禁令>

## 版式约定

- <如：组合图不锁死分格数；单张全景写前中远景深层次>

## 已定决策查证来源

| 决策类型 | 查哪里 |
|---|---|
| 比例 / 尺寸 | <你项目的尺寸规格文档> |
| 形象特征 | <你项目的角色/设定资料> |
| 结构与开合方式 | <你项目的设定文本> |
