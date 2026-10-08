# Coordinate-box Edit (Seedream 5.0 Pro interactive edit)

> Applies when: you need to make a local modification to an **already generated image** (replace/add/change some spot) without repainting the whole image.
> Tested channel: `volcengine` · `doubao-seedream-5-0-pro-260628` (verified working on 2026-09-25).

## Mechanism (the key: there is no API field)

Seedream's "interactive edit" is **not** an API parameter, but **normalized coordinates written in the prompt text**:

- Format: `Image N x1 y1 x2 y2` (N = reference-image index, starting from 1); for a point selection it is `Image N x y`.
- Coordinate range **0–999**, top-left `0 0`, bottom-right `999 999`; convert with `x = round(x_px / width * 1000)`.
- Official example: `Replace the area Image 1 120 180 640 760 with a garden.`
- If you **draw marks** on the image (box/arrow/doodle) before uploading, you **must** write "remove all sketch lines" in the prompt, otherwise the marks are rendered as image elements.

## Companion workflow

1. Use `scripts/mask_editor.py` to open the base image and box-select the target region (the aspect-ratio lock on the toolbar can directly lock `16:9`/`1:1` etc.; once locked, both drawing and dragging handles follow that ratio; turn off "feather" when saving to get an exact boundary). **Multiple discontinuous regions can be stacked** — each rectangle/ellipse/brush you draw is an independent selection, and the "selection list" on the right lets you click-select, delete individually (`Delete` key or "delete selected"), and step-undo with `Ctrl+Z`. Note that `bbox_from_mask.py` takes the **bounding box of the union of all selections**, so for a coordinate-edit scenario boxing just one region is cleanest;
2. Use `scripts/bbox_from_mask.py` to reverse-solve the mask into normalized coordinates;
3. Write the coordinates into the prompt, together with the "what to change / what to keep unchanged" instruction (see "prompt writing template" below);
4. Generate with `volcengine` (note: on this path `size` must match the base image's canvas).

## Tested conclusions (2026-09-25)

- ✅ **Coordinate-box selection works**: content outside the specified region (door, mountain body, passage, light and shadow, composition) **stays unchanged**.
- ⚠️ **"Proportional scaling" is executed incompletely**: for the instruction `shrink both beasts in the region to 1/2 overall`, the model did a local repaint, the beasts were **noticeably smaller but not exactly halved**, and the target objects' **pose may be rewritten** (the cub went from "biting rebar and pulling back while seated" to "standing and sniffing").
- Conclusion: **this capability is good at "replace / repaint / add within a region", not at "precise proportional scaling"**.
  - Need precise scaling → use the **compositing method** (locally scaled texture), or scale the reference first and then edit.
  - When using a coordinate box, **write the target form and pose together clearly** (treat it as "repaint an X in this region"), which is more reliable than writing "shrink/move X".

## Prompt writing template

```
【Interactive edit instruction · core】
Within the region Image 1 <x1> <y1> <x2> <y2>, <change description> (write the target form, pose, and proportions together clearly).
Fill the space freed by the shrink/change naturally with the original <ground/rock wall/background>.

【Keep unchanged · hard constraint】
All content outside this region stays strictly unchanged: <subject structure, light and shadow, composition, camera position, canvas>.

【Hard exclusions】no text, no watermark, no sketch lines.
```
