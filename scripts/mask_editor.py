#!/usr/bin/env python3
"""Interactive mask editor: opens a browser window to paint the repaint area.

Usage:
  python mask_editor.py --image <base.png> --out <mask.png> [--port 8765]

Two uses:
  1. Repaint mask (heyroute/OpenAI edits): painted area = transparent (alpha 0,
     repainted), rest = opaque (kept). Painted area is shown as translucent red.
  2. Region picker for coordinate edit (Seedream): draw one or more rectangles and
     feed the saved PNG to scripts/bbox_from_mask.py to get normalized 0-999
     coordinates for the prompt. Disable the feather checkbox for exact bounds.

Multiple selections stack: every rectangle / ellipse / polygon / brush stroke is
its own selectable item (S.items). Click a shape (or a row in the 选区列表 panel)
to select it, press Delete or click 删除选中 to remove just that one, and Ctrl+Z
undoes one step. A polygon is built by clicking point after point and closing it
with a double click (or by clicking its first vertex again); Backspace drops the
last point and Esc discards the draft. The exported mask is still a single
black/white bitmap union, so downstream --mask / bbox_from_mask.py need no changes.

Feather (8px blur) is a UI checkbox, applied on save.
"""
import argparse
import base64
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Mask Editor</title>
<style>
  body { margin:0; background:#1b1b1f; color:#ddd; font:14px/1.4 system-ui; overflow:hidden; }
  #bar { position:fixed; top:0; left:0; right:0; z-index:10; background:#26262c;
         padding:8px 12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;
         border-bottom:1px solid #3a3a42; }
  button { background:#3a3a44; color:#eee; border:1px solid #55555f; border-radius:6px;
           padding:6px 11px; cursor:pointer; font:inherit; }
  button:hover { background:#46464e; }
  button.on { background:#a33; border-color:#d55; }
  button.r.on { background:#255a8f; border-color:#4a8fd0; }
  button:disabled { opacity:.45; cursor:default; }
  .grp { display:flex; gap:6px; align-items:center; padding-right:9px;
         border-right:1px solid #3a3a42; }
  label { color:#9aa; white-space:nowrap; }
  input[type=number] { width:70px; background:#111; color:#eee; border:1px solid #55555f;
                       border-radius:4px; padding:4px 5px; font:inherit; }
  input[type=number]:disabled { color:#666; background:#1d1d21; }
  input[type=range] { width:96px; }
  #stage { position:absolute; left:0; right:0; bottom:0; top:52px; overflow:hidden;
           background:#141417; }
  #img, #ov { position:absolute; left:0; top:0; }
  #img { z-index:1; } #ov { z-index:2; }
  #hint { position:fixed; bottom:10px; left:12px; z-index:10; background:#000a;
          padding:7px 10px; border-radius:6px; max-width:64vw; font-size:12.5px; }
  #stat { position:fixed; bottom:10px; right:12px; z-index:10; background:#000a;
          padding:7px 10px; border-radius:6px; text-align:right; font-size:12.5px;
          line-height:1.7; }
  #stat i { color:#8fb4d8; font-style:normal; }
  #stat b { color:#ffd479; font-weight:600; }
  #msg { color:#8f8; font-size:12.5px; }
  #list { position:fixed; top:60px; right:10px; z-index:11; background:#24242acc;
          border:1px solid #44444c; border-radius:8px; padding:6px; min-width:190px;
          max-height:52vh; overflow:auto; font-size:12.5px; }
  #list h4 { margin:2px 4px 6px; font-size:12px; color:#9aa; font-weight:600; }
  #list .row { display:flex; align-items:center; gap:6px; padding:3px 5px; border-radius:5px;
               cursor:pointer; white-space:nowrap; }
  #list .row:hover { background:#3a3a44; }
  #list .row.on { background:#255a8f; }
  #list .row .nm { flex:1; }
  #list .row .del { color:#f88; font-weight:700; padding:0 4px; }
  #list .row .del:hover { color:#f33; }
  #list .empty { color:#777; padding:3px 5px; }
</style>
</head>
<body>
<div id="bar">
  <div class="grp">
    <button id="tRect" class="on">矩形</button>
    <button id="tEll">椭圆</button>
    <button id="tPoly">多边形</button>
    <button id="tBrush">画笔</button>
    <button id="tEraser">橡皮</button>
  </div>
  <div class="grp" id="ratios">
    <label>比例</label>
    <button class="r on" data-r="0">自由</button>
    <button class="r" data-r="1">1:1</button>
    <button class="r" data-r="1.3333333333">4:3</button>
    <button class="r" data-r="1.5">3:2</button>
    <button class="r" data-r="1.7777777778">16:9</button>
    <button class="r" data-r="2.3333333333">21:9</button>
  </div>
  <div class="grp">
    <label>X <input type="number" id="ix" step="1"></label>
    <label>Y <input type="number" id="iy" step="1"></label>
    <label>W <input type="number" id="iw" step="1"></label>
    <label>H <input type="number" id="ih" step="1"></label>
  </div>
  <div class="grp">
    <label>笔刷 <input type="range" id="brush" min="4" max="120" value="40"></label>
    <label><input type="checkbox" id="feather" checked> 羽化</label>
  </div>
  <div class="grp">
    <button id="delSel" title="删除选中选区 (Delete)">删除选中</button>
    <button id="undo">撤销</button>
    <button id="clear">清空</button>
    <button id="zout" title="缩小 (Ctrl+滚轮)">−</button>
    <button id="zin" title="放大 (Ctrl+滚轮)">＋</button>
    <button id="fit" title="双击画布同效">适配</button>
  </div>
  <div class="grp">
    <button id="save" style="background:#276">保存蒙版</button>
    <span id="msg"></span>
  </div>
</div>
<div id="stage"><img id="img"><canvas id="ov"></canvas></div>
<div id="list"><h4>选区列表</h4><div id="listBody"></div></div>
<div id="hint">矩形/椭圆：拖手柄改大小（锁比例时等比）、拖框内移动、点手柄选中后可用方向键推拉。
多边形：单击逐点落点、双击或点回起点闭合；绘制中 Backspace 退一点、Esc 放弃；闭合后是独立选区。
多个选区可叠加：新画一个不会清掉旧的。点击选中某个选区后，按 Delete 或点「删除选中」删掉它。
画笔/橡皮拖拽绘制；按住 Alt 点击可选中已有选区。
比例按钮锁死后绘制/编辑都受约束。Ctrl+滚轮缩放、中键或空格+拖拽平移、双击适配。
方向键=微调 1px，Shift+方向键=10px，Esc 取消手柄选中，Ctrl+Z 撤销。</div>
<div id="stat">
  <div><i>对象</i> <b id="sTarget">无选区</b></div>
  <div><i>尺寸</i> <b id="sSize">—</b> <span id="sImg"></span></div>
  <div><i>比例</i> <b id="sRatio">—</b></div>
  <div><i>归一化</i> <b id="sNorm">—</b></div>
  <div><i>选区数</i> <b id="sCount">0</b></div>
</div>
<script>
const img = document.getElementById('img');
const ov = document.getElementById('ov');
const octx = ov.getContext('2d');
const stage = document.getElementById('stage');
const bar = document.getElementById('bar');
const sel = document.createElement('canvas');
const sctx = sel.getContext('2d');

const S = {
  tool: 'rect', ratio: null, ratioLabel: '自由',
  items: [], selId: null, nextId: 1, handle: null, drag: null, hist: [],
  draft: null, cursor: null, view: { k: 1, tx: 0, ty: 0 }, space: false,
};
function boxKind(it) { return it && (it.kind === 'rect' || it.kind === 'ell'); }
Object.defineProperty(S, 'box', {
  get() { const it = selItem(); return boxKind(it) ? it.box : null; },
  set(v) { const it = selItem(); if (boxKind(it)) it.box = v; },
});
function selItem() { return S.items.find(i => i.id === S.selId) || null; }
const MIN = 12;
const HIT = 8;
const HANDLE_PX = 7;
const TINT_ALPHA = 110;   // 0-255; the one source of the selection tint's opacity
const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const HANDLE_LABEL = { n:'上边', s:'下边', e:'右边', w:'左边', ne:'右上角', nw:'左上角', se:'右下角', sw:'左下角' };

img.src = '/image?' + Date.now();
img.onload = () => {
  sel.width = img.naturalWidth;
  sel.height = img.naturalHeight;
  sctx.fillStyle = '#fff';
  sctx.fillRect(0, 0, sel.width, sel.height);
  fitView();
  updateInfo();
  updateInputs();
};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function clampBox(b) {
  const W = sel.width, H = sel.height;
  b.w = clamp(b.w, MIN, W);
  b.h = clamp(b.h, MIN, H);
  b.x = clamp(b.x, 0, W - b.w);
  b.y = clamp(b.y, 0, H - b.h);
  return b;
}

function inside(b, p) { return p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h; }

function handlePoint(b, h) {
  const x2 = b.x + b.w, y2 = b.y + b.h, cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  if (h === 'nw') return { x: b.x, y: b.y };
  if (h === 'ne') return { x: x2, y: b.y };
  if (h === 'se') return { x: x2, y: y2 };
  if (h === 'sw') return { x: b.x, y: y2 };
  if (h === 'n') return { x: cx, y: b.y };
  if (h === 's') return { x: cx, y: y2 };
  if (h === 'e') return { x: x2, y: cy };
  return { x: b.x, y: cy };
}

function handleAt(p) {
  const b = S.box;
  if (!b) return null;
  const tol = HIT / S.view.k;
  for (const h of HANDLES) {
    const hp = handlePoint(b, h);
    if (Math.abs(p.x - hp.x) <= tol && Math.abs(p.y - hp.y) <= tol) return h;
  }
  return inside(b, p) ? 'move' : null;
}

function pointInPoly(pts, p) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i], b = pts[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

function shapeAt(p) {
  for (let i = S.items.length - 1; i >= 0; i--) {
    const it = S.items[i];
    if (it.kind === 'brush' || it.kind === 'eraser') {
      for (const s of it.strokes) {
        if (Math.hypot(p.x - s.x, p.y - s.y) <= s.r) return it;
      }
    } else if (it.kind === 'poly') {
      if ((it.points || []).length >= 3 && pointInPoly(it.points, p)) return it;
    } else if (it.box && inside(it.box, p)) {
      return it;
    }
  }
  return null;
}

function fitInImage(x, y, w, h, ratio) {
  const W = sel.width, H = sel.height;
  w = Math.max(w, MIN); h = w / ratio;
  if (h > H) { h = H; w = h * ratio; }
  if (w > W) { w = W; h = w / ratio; }
  return { x: clamp(x, 0, W - w), y: clamp(y, 0, H - h), w, h };
}

function fitRatioIn(b, ratio) {
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  let w, h;
  if (b.w / b.h > ratio) { h = b.h; w = h * ratio; } else { w = b.w; h = w / ratio; }
  if (w > b.w) { w = b.w; h = w / ratio; }
  if (h > b.h) { h = b.h; w = h * ratio; }
  return fitInImage(cx - w / 2, cy - h / 2, w, h, ratio);
}

function reshapeForRatio() {
  if (S.ratio && S.box) S.box = fitRatioIn(S.box, S.ratio);
}

function resizeBox(base, hd, p, ratio) {
  const W = sel.width, H = sel.height;
  const x = base.x, y = base.y, w = base.w, hh = base.h;
  const x2 = x + w, y2 = y + hh;
  let nx = x, ny = y, nx2 = x2, ny2 = y2;
  if (hd.includes('w')) nx = p.x;
  if (hd.includes('e')) nx2 = p.x;
  if (hd.includes('n')) ny = p.y;
  if (hd.includes('s')) ny2 = p.y;
  nx = clamp(nx, 0, W); nx2 = clamp(nx2, 0, W);
  ny = clamp(ny, 0, H); ny2 = clamp(ny2, 0, H);

  if (!ratio) {
    if (nx2 - nx < MIN) { if (hd.includes('w')) nx = nx2 - MIN; else nx2 = nx + MIN; }
    if (ny2 - ny < MIN) { if (hd.includes('n')) ny = ny2 - MIN; else ny2 = ny + MIN; }
    return clampBox({ x: nx, y: ny, w: nx2 - nx, h: ny2 - ny });
  }

  if (hd.length === 2) {
    const ax = hd.includes('w') ? x2 : x;
    const ay = hd.includes('n') ? y2 : y;
    let w2 = Math.abs(p.x - ax), h2 = Math.abs(p.y - ay);
    if (w2 / ratio >= h2) h2 = w2 / ratio; else w2 = h2 * ratio;
    const bx = hd.includes('w') ? ax - w2 : ax;
    const by = hd.includes('n') ? ay - h2 : ay;
    return fitInImage(bx, by, w2, h2, ratio);
  }

  const cx = x + w / 2, cy = y + hh / 2;
  if (hd === 'e' || hd === 'w') {
    const w2 = Math.max(MIN, Math.abs(nx2 - nx));
    const h2 = w2 / ratio;
    return fitInImage(hd === 'e' ? x : nx2 - w2, cy - h2 / 2, w2, h2, ratio);
  }
  const h2 = Math.max(MIN, Math.abs(ny2 - ny));
  const w2 = h2 * ratio;
  return fitInImage(cx - w2 / 2, hd === 's' ? y : ny2 - h2, w2, h2, ratio);
}

function createBox(a, b, ratio) {
  if (!ratio) {
    const w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
    if (w < 1 || h < 1) return null;
    return clampBox({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w, h });
  }
  const horiz = Math.abs(b.x - a.x) >= Math.abs(b.y - a.y);
  let w2 = Math.abs(b.x - a.x), h2 = Math.abs(b.y - a.y);
  if (horiz) h2 = w2 / ratio; else w2 = h2 * ratio;
  if (w2 < 2 || h2 < 2) return null;
  const sx = b.x < a.x ? -1 : 1, sy = b.y < a.y ? -1 : 1;
  return fitInImage(sx > 0 ? a.x : a.x - w2, sy > 0 ? a.y : a.y - h2, w2, h2, ratio);
}

function strokePath(c, strokes, s) {
  if (!strokes.length) return;
  s = s || 1;
  c.lineCap = 'round';
  c.lineJoin = 'round';
  if (strokes.length === 1) {
    const p = strokes[0];
    c.lineWidth = p.r * 2 * s;
    c.beginPath();
    c.moveTo(p.x * s, p.y * s);
    c.lineTo(p.x * s + 0.01, p.y * s);   // a dot still paints with round caps
    c.stroke();
    return;
  }
  // Segment by segment: each sample carries its own radius, and connecting the
  // samples is what turns sparse clicks into a continuous stroke (drawing only
  // arcs left visible gaps whenever the pointer moved faster than the brush).
  for (let i = 1; i < strokes.length; i++) {
    const a = strokes[i - 1], b = strokes[i];
    c.lineWidth = (a.r + b.r) * s;
    c.beginPath();
    c.moveTo(a.x * s, a.y * s);
    c.lineTo(b.x * s, b.y * s);
    c.stroke();
  }
}

function drawItem(c, it) {
  if (it.kind === 'brush' || it.kind === 'eraser') {
    c.save();
    c.globalCompositeOperation = it.kind === 'eraser' ? 'destination-out' : 'source-over';
    c.strokeStyle = '#000';
    strokePath(c, it.strokes);
    c.restore();
    return;
  }
  c.fillStyle = '#000';
  if (it.kind === 'poly') {
    const pts = it.points || [];
    if (pts.length < 3) return;
    c.beginPath();
    c.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) c.lineTo(pts[i].x, pts[i].y);
    c.closePath();
    c.fill();
  } else if (it.kind === 'ell') {
    const b = it.box;
    if (!b) return;
    c.beginPath();
    c.ellipse(b.x + b.w / 2, b.y + b.h / 2, b.w / 2, b.h / 2, 0, 0, Math.PI * 2);
    c.fill();
  } else if (it.kind === 'rect') {
    const b = it.box;
    if (!b) return;
    c.fillRect(b.x, b.y, b.w, b.h);
  }
  // No fallback: an unknown kind must not silently render as a rectangle. A
  // new kind that forgets this branch leaves a visible hole instead of a
  // plausible-but-wrong shape.
}

function syncSel() {
  sctx.globalCompositeOperation = 'source-over';
  sctx.fillStyle = '#fff';
  sctx.fillRect(0, 0, sel.width, sel.height);
  for (const it of S.items) drawItem(sctx, it);
  sctx.globalCompositeOperation = 'source-over';
  S.overlayDirty = true;
}

function makeOverlay() {
  // Build the translucent-red view of `sel` once and reuse it. Rebuilding costs
  // a full-canvas getImageData (~20ms), which is what made a brush drag feel
  // like a slideshow, so it is rebuilt only after the mask actually changes.
  if (S.overlayDirty || !S.overlay) {
    const tmp = document.createElement('canvas');
    tmp.width = sel.width; tmp.height = sel.height;
    const tctx = tmp.getContext('2d');
    tctx.drawImage(sel, 0, 0);
    const data = tctx.getImageData(0, 0, tmp.width, tmp.height);
    const px = data.data;
    for (let i = 0; i < px.length; i += 4) {
      // Scale the tint by the mask's own coverage so an anti-aliased edge fades
      // out instead of ending on a hard line, capped at TINT_ALPHA.
      px[i] = 255; px[i + 1] = 0; px[i + 2] = 0;
      px[i + 3] = Math.round((1 - px[i] / 255) * TINT_ALPHA);
    }
    tctx.putImageData(data, 0, 0);
    S.overlay = tmp;
    S.overlayDirty = false;
  }
  return S.overlay;
}

function overlaySel() {
  const tmp = makeOverlay();
  octx.imageSmoothingEnabled = false;
  octx.drawImage(tmp, 0, 0, ov.width, ov.height);
  octx.imageSmoothingEnabled = true;
}

function layout() {
  stage.style.top = bar.offsetHeight + 'px';
  const k = S.view.k;
  const w = sel.width * k, h = sel.height * k;
  img.style.width = ov.style.width = w + 'px';
  img.style.height = ov.style.height = h + 'px';
  img.style.left = ov.style.left = S.view.tx + 'px';
  img.style.top = ov.style.top = S.view.ty + 'px';
  ov.width = Math.max(1, Math.round(w));
  ov.height = Math.max(1, Math.round(h));
  render();
}

function fitView() {
  stage.style.top = bar.offsetHeight + 'px';
  const r = stage.getBoundingClientRect();
  const k = Math.min(r.width / sel.width, r.height / sel.height);
  S.view.k = k;
  S.view.tx = (r.width - sel.width * k) / 2;
  S.view.ty = (r.height - sel.height * k) / 2;
  layout();
}

function outlineItem(it) {
  const k = S.view.k;
  const on = it.id === S.selId;
  if (it.kind === 'brush' || it.kind === 'eraser') {
    // Outline the stroke the same way the mask is painted: one connected path,
    // not one circle per sample (which read as a string of disconnected rings).
    octx.strokeStyle = on ? (it.kind === 'eraser' ? '#ff8a8a' : '#4ad6ff') : '#d6a44a';
    octx.lineWidth = on ? 2 : 1.25;
    octx.save();
    octx.globalAlpha = 0.9;
    strokePath(octx, it.strokes, S.view.k);
    octx.restore();
    return;
  }
  if (!it.box) {
    if (it.kind === 'poly' && on) {
      drawPolyOutline(it.points || [], false);
    }
    return;
  }
  const b = it.box;
  octx.strokeStyle = on ? '#4ad6ff' : '#d6a44a';
  octx.lineWidth = on ? 2 : 1.25;
  if (it.kind === 'ell') {
    octx.beginPath();
    octx.ellipse((b.x + b.w / 2) * k, (b.y + b.h / 2) * k, b.w / 2 * k, b.h / 2 * k, 0, 0, Math.PI * 2);
    octx.stroke();
  } else {
    octx.strokeRect(b.x * k, b.y * k, b.w * k, b.h * k);
  }
}

function drawPolyOutline(pts, withCursor) {
  const k = S.view.k;
  if (!pts.length) return;
  octx.strokeStyle = '#4ad6ff';
  octx.lineWidth = 2;
  octx.beginPath();
  octx.moveTo(pts[0].x * k, pts[0].y * k);
  for (let i = 1; i < pts.length; i++) octx.lineTo(pts[i].x * k, pts[i].y * k);
  if (withCursor && S.cursor) octx.lineTo(S.cursor.x * k, S.cursor.y * k);
  octx.stroke();
  octx.fillStyle = '#fff';
  for (const p of pts) {
    octx.fillRect(p.x * k - 3, p.y * k - 3, 6, 6);
  }
}

function render() {
  octx.clearRect(0, 0, ov.width, ov.height);
  overlaySel();
  for (const it of S.items) outlineItem(it);

  if (S.draft && S.draft.points.length) drawPolyOutline(S.draft.points, true);

  const b = S.box;
  if (b && S.selId !== null) {
    const k = S.view.k;
    for (const h of HANDLES) {
      const p = handlePoint(b, h);
      const s = HANDLE_PX;
      octx.fillStyle = S.handle === h ? '#ff5252' : '#fff';
      octx.lineWidth = 1.5;
      octx.fillRect(p.x * k - s / 2, p.y * k - s / 2, s, s);
      octx.strokeRect(p.x * k - s / 2, p.y * k - s / 2, s, s);
    }
  }
}

function pos(e) {
  const r = stage.getBoundingClientRect();
  return {
    x: (e.clientX - r.left - S.view.tx) / S.view.k,
    y: (e.clientY - r.top - S.view.ty) / S.view.k,
  };
}

function snap() {
  return JSON.stringify({ items: S.items, selId: S.selId, nextId: S.nextId });
}

function pushHist() {
  S.hist.push(snap());
  if (S.hist.length > 60) S.hist.shift();
  document.getElementById('undo').disabled = S.hist.length === 0;
}

function undo() {
  if (!S.hist.length) return;
  const st = JSON.parse(S.hist.pop());
  S.items = st.items;
  S.selId = st.selId;
  S.nextId = st.nextId;
  S.handle = null;
  syncSel();
  syncAll();
  document.getElementById('undo').disabled = S.hist.length === 0;
}

function clearAll() {
  if (!S.items.length && !S.draft) return;
  pushHist();
  S.items = [];
  S.selId = null;
  S.handle = null;
  S.draft = null;
  S.cursor = null;
  syncSel();
  syncAll();
}

function dropItem(id) {
  S.items = S.items.filter(x => x.id !== id);
  if (S.selId === id) S.selId = null;
  S.handle = null;
}

function removeItem(id) {
  dropItem(id);
  syncSel();
  syncAll();
}

function deleteSelected() {
  if (S.selId === null) return;
  pushHist();
  removeItem(S.selId);
}

function itemLabel(it) {
  const k = { rect: '矩形', ell: '椭圆', poly: '多边形', brush: '画笔', eraser: '橡皮' }[it.kind] || it.kind;
  if (it.kind === 'brush' || it.kind === 'eraser') return k + ' ' + it.strokes.length + ' 点';
  if (it.kind === 'poly') return k + ' ' + (it.points || []).length + ' 个顶点';
  const b = it.box;
  if (!b) return k + ' —';
  return k + ' ' + Math.round(b.w) + '×' + Math.round(b.h);
}

function renderList() {
  const body = document.getElementById('listBody');
  body.innerHTML = '';
  if (!S.items.length) {
    const d = document.createElement('div');
    d.className = 'empty';
    d.textContent = '（还没有选区）';
    body.appendChild(d);
    return;
  }
  for (const it of S.items) {
    const row = document.createElement('div');
    row.className = 'row' + (it.id === S.selId ? ' on' : '');
    row.dataset.id = String(it.id);
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = '#' + it.id + ' · ' + itemLabel(it);
    nm.onclick = () => { S.selId = it.id; S.handle = null; render(); updateInfo(); updateInputs(); renderList(); };
    const del = document.createElement('span');
    del.className = 'del';
    del.textContent = '×';
    del.title = '删除这个选区';
    del.onclick = ev => {
      ev.stopPropagation();
      pushHist();
      removeItem(it.id);
    };
    row.appendChild(nm);
    row.appendChild(del);
    body.appendChild(row);
  }
}

function updateListCounts() {
  const body = document.getElementById('listBody');
  for (const it of S.items) {
    const row = body.querySelector('.row[data-id="' + it.id + '"]');
    if (!row) continue;
    const nm = row.querySelector('.nm');
    if (nm) nm.textContent = '#' + it.id + ' · ' + itemLabel(it);
    row.classList.toggle('on', it.id === S.selId);
  }
}

function syncAll() {
  layout();
  updateInfo();
  updateInputs();
  renderList();
}

function updateInfo() {
  const b = S.box;
  const it = selItem();
  const drawing = S.draft ? ' (绘制中: ' + S.draft.points.length + ' 点, 双击闭合)' : '';
  document.getElementById('sTarget').textContent =
    S.handle ? HANDLE_LABEL[S.handle] : (it ? itemLabel(it) : (S.draft ? '多边形' + drawing : '无选区'));
  document.getElementById('sImg').textContent =
    '(图 ' + sel.width + '×' + sel.height + ')';
  document.getElementById('sCount').textContent = String(S.items.length);
  if (!b) {
    if (it && (it.kind === 'brush' || it.kind === 'eraser')) {
      document.getElementById('sSize').textContent = it.strokes.length + ' 点';
    } else if (it && it.kind === 'poly') {
      document.getElementById('sSize').textContent = (it.points || []).length + ' 个顶点';
    } else if (S.draft) {
      document.getElementById('sSize').textContent = S.draft.points.length + ' 点';
    } else {
      document.getElementById('sSize').textContent = '—';
    }
    document.getElementById('sRatio').textContent = '—';
    document.getElementById('sNorm').textContent = '—';
    return;
  }
  document.getElementById('sSize').textContent = Math.round(b.w) + '×' + Math.round(b.h);
  document.getElementById('sRatio').textContent =
    (b.w / b.h).toFixed(4) + '  [' + (S.ratio ? S.ratioLabel : '自由') + ']';
  const n = v => Math.round(v);
  document.getElementById('sNorm').textContent = [
    n(b.x), n(b.y), n(b.x + b.w), n(b.y + b.h),
  ].join(' ') + '  →  ' + [
    Math.round(b.x / sel.width * 1000), Math.round(b.y / sel.height * 1000),
    Math.round((b.x + b.w) / sel.width * 1000), Math.round((b.y + b.h) / sel.height * 1000),
  ].join(' ');
}

function updateInputs() {
  const b = S.box;
  ['ix', 'iy', 'iw', 'ih'].forEach(id => { document.getElementById(id).value = ''; });
  if (b) {
    document.getElementById('ix').value = Math.round(b.x);
    document.getElementById('iy').value = Math.round(b.y);
    document.getElementById('iw').value = Math.round(b.w);
    document.getElementById('ih').value = Math.round(b.h);
  }
  const lock = !!S.ratio;
  document.getElementById('ix').disabled = !b;
  document.getElementById('iy').disabled = !b;
  document.getElementById('iw').disabled = !b;
  document.getElementById('ih').disabled = !b || lock;
}

function applyInputs() {
  if (!S.box) return;
  const v = id => parseInt(document.getElementById(id).value, 10);
  const nb = { ...S.box };
  const x = v('ix'), y = v('iy'), w = v('iw'), h = v('ih');
  if (!isNaN(x)) nb.x = x;
  if (!isNaN(y)) nb.y = y;
  if (!isNaN(w) && w > 0) nb.w = w;
  if (S.ratio) {
    if (!isNaN(w) && w > 0) nb.h = w / S.ratio;
  } else if (!isNaN(h) && h > 0) {
    nb.h = h;
  }
  pushHist();
  S.box = clampBox(nb);
  S.handle = null;
  syncSel();
  syncAll();
}

function setBox(b) {
  const it = selItem();
  if (it) it.box = b;
  syncSel();
  render();
  updateInfo();
  updateInputs();
  updateListCounts();
}

function cursorFor(h) {
  if (h === 'move') return 'move';
  if (h === 'n' || h === 's') return 'ns-resize';
  if (h === 'e' || h === 'w') return 'ew-resize';
  if (h === 'nw' || h === 'se') return 'nwse-resize';
  if (h === 'ne' || h === 'sw') return 'nesw-resize';
  return 'crosshair';
}

function isBoxTool(t) { t = t || S.tool; return t === 'rect' || t === 'ell'; }
function isBoxItem(it) { return it && (it.kind === 'rect' || it.kind === 'ell'); }

function newItem(kind) {
  const it = { id: S.nextId++, kind, box: null, strokes: [], points: [] };
  S.items.push(it);
  return it;
}

function refresh() {
  render();
  updateInfo();
  updateInputs();
  updateListCounts();
}

function polyAddPoint(p) {
  if (!S.draft) S.draft = { points: [] };
  S.draft.points.push({ x: p.x, y: p.y });
  S.selId = null;
  refresh();
  renderList();
}

function polyFinish() {
  const d = S.draft;
  S.draft = null;
  S.cursor = null;
  if (!d || d.points.length < 3) { render(); syncAll(); return; }
  pushHist();
  const it = newItem('poly');
  it.points = d.points;
  S.selId = it.id;
  syncSel();
  syncAll();
}

function polyCancel() {
  if (!S.draft) return false;
  S.draft = null;
  S.cursor = null;
  refresh();
  return true;
}

ov.addEventListener('mousedown', e => {
  const p = pos(e);
  if (e.button === 1 || (e.button === 0 && S.space)) {
    S.drag = { mode: 'pan', sx: e.clientX, sy: e.clientY, tx: S.view.tx, ty: S.view.ty };
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;
  if (S.tool === 'poly') {
    if (S.draft && S.draft.points.length >= 3) {
      const first = S.draft.points[0];
      if (Math.hypot(p.x - first.x, p.y - first.y) <= HIT / S.view.k) {
        polyFinish();
        return;
      }
    }
    polyAddPoint(p);
    return;
  }
  if (S.tool === 'brush' || S.tool === 'eraser') {
    // Brush/eraser paint by default, but Alt+click picks an existing selection
    // instead of drawing - so a brush user can still select what they drew.
    if (e.altKey) {
      const hitShape = shapeAt(p);
      if (hitShape) {
        S.selId = hitShape.id;
        S.handle = null;
        render();
        updateInfo();
        updateInputs();
        renderList();
        return;
      }
    }
    pushHist();
    S.drag = { mode: 'paint' };
    paint(p);
    return;
  }
  const hit = handleAt(p);
  if (hit && hit !== 'move') {
    pushHist();
    S.drag = { mode: 'resize', handle: hit, base: { ...S.box } };
    S.handle = hit;
    syncAll();
    return;
  }
  if (hit === 'move') {
    pushHist();
    S.drag = { mode: 'move', base: { ...S.box }, ox: p.x, oy: p.y };
    S.handle = null;
    syncAll();
    return;
  }
  const target = shapeAt(p);
  if (target) {
    S.selId = target.id;
    S.handle = null;
    if (isBoxItem(target)) {
      pushHist();
      S.drag = { mode: 'move', base: { ...target.box }, ox: p.x, oy: p.y };
    } else {
      S.drag = null;
    }
    render();
    updateInfo();
    updateInputs();
    renderList();
    return;
  }
  pushHist();
  S.handle = null;
  S.drag = { mode: 'create', a: p };
  const draft = newItem(S.tool === 'ell' ? 'ell' : 'rect');
  S.selId = draft.id;
  syncSel();
  updateInfo();
  updateInputs();
  renderList();
});

window.addEventListener('mousemove', e => {
  const p = pos(e);
  if (!S.drag) {
    if (S.tool === 'poly' && S.draft) {
      S.cursor = { x: p.x, y: p.y };
      ov.style.cursor = 'crosshair';
      render();
      return;
    }
    const hit = isBoxTool() ? handleAt(p) : null;
    ov.style.cursor = S.space ? 'grab' : (hit ? cursorFor(hit) : (shapeAt(p) ? 'move' : 'crosshair'));
    return;
  }
  if (S.drag.mode === 'pan') {
    S.view.tx = S.drag.tx + (e.clientX - S.drag.sx);
    S.view.ty = S.drag.ty + (e.clientY - S.drag.sy);
    layout();
    return;
  }
  if (S.drag.mode === 'paint') { paint(p); return; }
  if (S.drag.mode === 'create') {
    const b = createBox(S.drag.a, p, S.ratio);
    if (b) setBox(b);
    return;
  }
  if (S.drag.mode === 'move') {
    const d = { x: p.x - S.drag.ox, y: p.y - S.drag.oy };
    setBox(clampBox({ x: S.drag.base.x + d.x, y: S.drag.base.y + d.y, w: S.drag.base.w, h: S.drag.base.h }));
    return;
  }
  if (S.drag.mode === 'resize') {
    setBox(resizeBox(S.drag.base, S.drag.handle, p, S.ratio));
  }
});

window.addEventListener('mouseup', () => {
  if (!S.drag) return;
  const wasCreate = S.drag.mode === 'create';
  S.drag = null;
  if (wasCreate) {
    const it = selItem();
    if (it && (!it.box || it.box.w < 2 || it.box.h < 2)) {
      dropItem(it.id);
      syncSel();
    }
  }
  syncAll();
});

function paint(p) {
  const b = +document.getElementById('brush').value;
  let it = selItem();
  const wantKind = S.tool === 'eraser' ? 'eraser' : 'brush';
  if (!it || it.kind !== wantKind) {
    it = newItem(wantKind);
    S.selId = it.id;
  }
  const before = it.strokes.length;
  it.strokes = extendStrokes(it.strokes, p, b);
  if (it.strokes.length > before) {
    // Stamp the newest segment onto the mask canvas (so the saved mask is right).
    const tail = it.strokes.slice(Math.max(0, before - 1));
    sctx.save();
    sctx.globalCompositeOperation = it.kind === 'eraser' ? 'destination-out' : 'source-over';
    sctx.strokeStyle = '#000';
    strokePath(sctx, tail, 1);
    sctx.restore();
    S.overlayDirty = true;

    if (it.kind === 'eraser') {
      // An eraser removes coverage, so there is nothing cheap to draw: the tint
      // has to be rebuilt to show the hole. Erasing is a low-frequency action,
      // so the full render is fine here.
      render();
    } else {
      // Brushes preview the new segment straight onto the overlay; rebuilding
      // the full-size tinted canvas on every pointer move made dragging stutter.
      const k = S.view.k;
      octx.save();
      octx.strokeStyle = 'rgba(255,0,0,' + (TINT_ALPHA / 255).toFixed(2) + ')';
      strokePath(octx, tail, k);
      octx.restore();
    }
    updateListCounts();
    return;
  }
  render();
  updateListCounts();
}

function extendStrokes(strokes, p, brushPx) {
  const r = brushPx / 2;
  if (!strokes.length) {
    strokes.push({ x: p.x, y: p.y, r: r });
    return strokes;
  }
  const last = strokes[strokes.length - 1];
  const d = Math.hypot(p.x - last.x, p.y - last.y);
  // Keep every sample unless it sits on top of the previous one. The old rule
  // ("skip the push and only move the last point") collapsed an entire drag
  // into a single travelling dot whenever the pointer moved slowly, because no
  // sample ever cleared the threshold - the stroke looked like one circle.
  if (d < 1.0) return strokes;
  strokes.push({ x: p.x, y: p.y, r: r });
  return strokes;
}

stage.addEventListener('wheel', e => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  const r = stage.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const nx = (mx - S.view.tx) / S.view.k;
  const ny = (my - S.view.ty) / S.view.k;
  const k2 = clamp(S.view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15), 0.08, 8);
  S.view.k = k2;
  S.view.tx = mx - nx * k2;
  S.view.ty = my - ny * k2;
  layout();
}, { passive: false });

function zoomBy(f) {
  const r = stage.getBoundingClientRect();
  const mx = r.width / 2, my = r.height / 2;
  const nx = (mx - S.view.tx) / S.view.k, ny = (my - S.view.ty) / S.view.k;
  const k2 = clamp(S.view.k * f, 0.08, 8);
  S.view.k = k2;
  S.view.tx = mx - nx * k2;
  S.view.ty = my - ny * k2;
  layout();
}

document.getElementById('zin').onclick = () => zoomBy(1.25);
document.getElementById('zout').onclick = () => zoomBy(1 / 1.25);
document.getElementById('fit').onclick = fitView;
ov.addEventListener('dblclick', e => {
  if (S.tool === 'poly' && S.draft) { e.preventDefault(); polyFinish(); return; }
  fitView();
});

document.addEventListener('keydown', e => {
  const t = e.target;
  const editing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
  if (e.code === 'Space' && !editing) {
    S.space = true;
    e.preventDefault();
  }
  if (editing) return;
  if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); undo(); return; }
  if (e.key === 'Escape') {
    if (polyCancel()) { e.preventDefault(); return; }
    S.handle = null;
    updateInfo();
    return;
  }
  if (S.tool === 'poly' && S.draft) {
    if (e.key === 'Backspace') {
      e.preventDefault();
      S.draft.points.pop();
      if (!S.draft.points.length) { S.draft = null; S.cursor = null; }
      refresh();
      return;
    }
    if (e.key === 'Enter') { e.preventDefault(); polyFinish(); return; }
  }
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteSelected(); return; }
  if (!isBoxTool()) return;
  const dirs = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (!dirs[e.key]) return;
  if (!S.box) return;
  e.preventDefault();
  const step = e.shiftKey ? 10 : 1;
  const [dx, dy] = dirs[e.key];
  if (S.handle && S.handle !== 'move') {
    const hp = handlePoint(S.box, S.handle);
    pushHist();
    setBox(resizeBox(S.box, S.handle, { x: hp.x + dx * step, y: hp.y + dy * step }, S.ratio));
    return;
  }
  pushHist();
  setBox(clampBox({ x: S.box.x + dx * step, y: S.box.y + dy * step, w: S.box.w, h: S.box.h }));
});

document.addEventListener('keyup', e => { if (e.code === 'Space') S.space = false; });

function setTool(t) {
  if (S.draft) polyCancel();
  S.tool = t;
  S.handle = null;
  for (const [id, tt] of [['tRect', 'rect'], ['tEll', 'ell'], ['tPoly', 'poly'], ['tBrush', 'brush'], ['tEraser', 'eraser']]) {
    document.getElementById(id).classList.toggle('on', tt === t);
  }
  syncAll();
}
document.getElementById('tRect').onclick = () => setTool('rect');
document.getElementById('tEll').onclick = () => setTool('ell');
document.getElementById('tPoly').onclick = () => setTool('poly');
document.getElementById('tBrush').onclick = () => setTool('brush');
document.getElementById('tEraser').onclick = () => setTool('eraser');

for (const btn of document.querySelectorAll('#ratios .r')) {
  btn.onclick = () => {
    for (const b2 of document.querySelectorAll('#ratios .r')) b2.classList.remove('on');
    btn.classList.add('on');
    const v = parseFloat(btn.dataset.r);
    S.ratio = v > 0 ? v : null;
    S.ratioLabel = btn.textContent;
    if (S.box && isBoxTool()) {
      pushHist();
      reshapeForRatio();
      syncSel();
    }
    syncAll();
  };
}

['ix', 'iy', 'iw', 'ih'].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener('change', applyInputs);
  el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyInputs(); } });
});

document.getElementById('undo').onclick = undo;
document.getElementById('delSel').onclick = deleteSelected;
document.getElementById('clear').onclick = clearAll;
document.getElementById('undo').disabled = true;

window.addEventListener('resize', layout);

document.getElementById('save').onclick = async () => {
  let src = sel;
  if (document.getElementById('feather').checked) {
    const f = document.createElement('canvas');
    f.width = sel.width; f.height = sel.height;
    const fc = f.getContext('2d');
    fc.filter = 'blur(8px)';
    fc.drawImage(sel, 0, 0);
    src = f;
  }
  const out = document.createElement('canvas');
  out.width = sel.width; out.height = sel.height;
  const octx2 = out.getContext('2d');
  const id = octx2.createImageData(out.width, out.height);
  const s = src.getContext('2d').getImageData(0, 0, src.width, src.height).data;
  for (let i = 0; i < id.data.length; i += 4) {
    id.data[i] = 255; id.data[i + 1] = 255; id.data[i + 2] = 255;
    id.data[i + 3] = s[i];
  }
  octx2.putImageData(id, 0, 0);
  const b64 = out.toDataURL('image/png').split(',')[1];
  try {
    const r = await fetch('/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ b64 }) });
    document.getElementById('msg').textContent = r.ok ? ' 已写入！关闭本页即可。' : ' 保存失败：服务器拒绝';
    if (r.ok) setTimeout(() => window.close(), 800);
  } catch (err) {
    document.getElementById('msg').textContent = ' 保存失败：' + err;
  }
};
</script>
</body>
</html>"""


_SRV = []  # module-level holder: [_HTTPServer] for graceful shutdown after save


def make_handler(image_path: Path, out_path: Path):
    img_bytes = image_path.read_bytes()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            # The page is regenerated from this file on every start, but a browser
            # will happily serve a cached copy from an earlier run - which looks
            # like "the editor is broken" (e.g. a brush tool that no longer paints
            # because the cached page predates the multi-selection rewrite).
            no_store = [("Cache-Control", "no-store, no-cache, must-revalidate"),
                        ("Pragma", "no-cache"), ("Expires", "0")]

            def head(ctype, length):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(length))
                for k, v in no_store:
                    self.send_header(k, v)
                self.end_headers()

            if self.path.startswith("/image"):
                head("image/png", len(img_bytes))
                self.wfile.write(img_bytes)
            else:
                data = HTML.encode("utf-8")
                head("text/html; charset=utf-8", len(data))
                self.wfile.write(data)

        def do_POST(self):
            if self.path != "/save":
                self.send_error(404)
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n))
                raw = payload["b64"]
                img_bytes_out = base64.b64decode(raw)
                out_path.write_bytes(img_bytes_out)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                body = f"bad request: {exc}".encode()
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            print(f"[mask_editor] mask written: {out_path}", flush=True)
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            threading.Thread(target=lambda: (time.sleep(1.0), _SRV[0].shutdown()),
                             daemon=True).start()

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    image_path = Path(args.image)
    out_path = Path(args.out)
    if not image_path.exists():
        sys.exit(f"image not found: {args.image}")

    handler = make_handler(image_path, out_path)
    try:
        srv = HTTPServer(("127.0.0.1", args.port), handler)
    except OSError:
        srv = HTTPServer(("127.0.0.1", args.port + 1), handler)
    _SRV.append(srv)
    port = srv.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"[mask_editor] open {url}  ->  save to {out_path}", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        # Headless / remote / sandboxed session: opening may fail silently or
        # raise. The URL above is printed unconditionally, so hand it to the
        # user instead of treating this as a failure.
        pass
    srv.serve_forever()


if __name__ == "__main__":
    main()
