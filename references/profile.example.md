---
# All optional; when omitted, SKILL.md's generic defaults apply
default_provider: heyroute
default_model: gpt-image-2
default_size: "16:9 1K"
output_naming: "assets/scratch/YYYYMMDD-HHMMSS-<slug>.jpg"
# Harness-level (only needed when bare `python` lacks requests+Pillow).
# Absolute path to an interpreter that has the skill's dependencies.
# Precedence: env var IMAGE_GENERATION_PYTHON > this key > bare `python`.
# Example: python: "C:/Users/<you>/.venvs/imagegen/Scripts/python.exe"
# python: ""
# Outbound HTTP(S) proxy for the scripts (optional). Read by generate.py itself.
# Precedence: --proxy > $IMAGE_GENERATION_PROXY > this key.
# Do NOT put credentials here - the profile is committed with the project;
# use $IMAGE_GENERATION_PROXY or --proxy for authenticated proxies.
# Example: proxy: "http://127.0.0.1:20171"
# proxy: ""
---

# Project Profile Example (Neutral)
**English** | [中文](profile.example.zh-CN.md)

> Copy this file to `<工程根>/.image-generation/profile.md` and fill it in for your own project.
> This file is only an example and does not represent any real project; the skill repo contains no active profile.

## Art Style (style paragraph template)

Example (neutral, replace as needed):
`Cinematic realistic rendering, soft natural lighting, medium saturation, restrained realism; no 2D illustration feel, no anime cel-shaded style.`

## Negative Words (pitfalls this project has hit)

- Distorted proportions
- Subject too small
- Panel/collage layout
- Text watermark
- <在此补充你项目踩过的坑>

## Structure and Articulation (past incidents)

- <如：漏写开合方式，反复生成错误结构——遇可动结构必须显式写运动方式并给反例禁令>

## Layout Conventions

- <如：组合图不锁死分格数；单张全景写前中远景深层次>

## Sources for Verifying Settled Decisions

| Decision type | Where to check |
|---|---|
| Ratio / size | <你项目的尺寸规格文档> |
| Appearance traits | <你项目的角色/设定资料> |
| Structure and articulation | <你项目的设定文本> |
