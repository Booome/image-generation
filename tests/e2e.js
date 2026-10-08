// Real E2E for mask_editor: draws, ratio-locks, resizes, moves, types, nudges,
// undoes, zooms and saves in a real Chromium, then reports failures.
const fs = require('fs');
const { chromium } = require('playwright');

const PORT = process.env.E2E_PORT || '8799';
const MASK = process.env.E2E_MASK;
const URL = `http://127.0.0.1:${PORT}/`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e.message)));
  page.on('console', m => { if (m.type() === 'error') pageErrors.push('console: ' + m.text()); });

  const fails = [];
  const check = (name, cond, detail) => {
    if (cond) console.log('  OK   ' + name);
    else { fails.push(name); console.log('  FAIL ' + name + (detail !== undefined ? '  -> ' + JSON.stringify(detail) : '')); }
  };

  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForFunction(() => document.getElementById('img').naturalWidth > 0);

  const box = () => page.evaluate(() => (S.box ? { x: S.box.x, y: S.box.y, w: S.box.w, h: S.box.h } : null));
  const view = () => page.evaluate(() => ({ k: S.view.k, tx: S.view.tx, ty: S.view.ty }));
  const info = () => page.evaluate(() => ({
    target: document.getElementById('sTarget').textContent,
    ratio: document.getElementById('sRatio').textContent,
    norm: document.getElementById('sNorm').textContent,
    size: document.getElementById('sSize').textContent,
  }));
  const geo = await page.evaluate(() => {
    const r = document.getElementById('ov').getBoundingClientRect();
    return { left: r.left, top: r.top, k: S.view.k, iw: sel.width, ih: sel.height };
  });
  const P = (nx, ny) => ({ x: geo.left + nx * geo.k, y: geo.top + ny * geo.k });
  const R169 = 16 / 9;
  const near = (a, b, eps) => Math.abs(a - b) <= (eps || 0.02);
  // Coordinates that made a round-trip through screen pixels can be off by up to
  // one screen pixel, which is 1/view.k image pixels.
  const nearScreen = (a, b) => Math.abs(a - b) <= 1.5 / geo.k + 0.5;

  console.log('image %dx%d, view.k=%s', geo.iw, geo.ih, geo.k.toFixed(3));

  // --- 1. lock 16:9 then draw ------------------------------------------------
  await page.click('#ratios .r[data-r="1.7777777778"]');
  check('16:9 button active', await page.evaluate(() => document.querySelector('#ratios .r[data-r="1.7777777778"]').classList.contains('on')));
  let a = P(200, 300), b = P(1000, 640);
  await page.mouse.move(a.x, a.y); await page.mouse.down();
  await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2); await page.mouse.move(b.x, b.y);
  await page.mouse.up();
  let bx = await box();
  check('draw: ratio locked to 16:9', bx && near(bx.w / bx.h, R169), bx && bx.w / bx.h);
  check('draw: anchored at start point', bx && nearScreen(bx.x, 200) && nearScreen(bx.y, 300), bx);
  check('draw: inside image', bx && bx.x >= 0 && bx.y >= 0 && bx.x + bx.w <= geo.iw && bx.y + bx.h <= geo.ih, bx);

  // --- 2. corner handle resize keeps ratio, opposite corner fixed -----------
  const se = P(bx.x + bx.w, bx.y + bx.h);
  await page.mouse.move(se.x, se.y); await page.mouse.down();
  await page.mouse.move(se.x + 120, se.y + 120);
  await page.mouse.up();
  let r = await box();
  check('resize SE: ratio kept', r && near(r.w / r.h, R169), r && r.w / r.h);
  check('resize SE: grew', r && r.w > bx.w, r && r.w);
  check('resize SE: NW corner fixed', r && near(r.x, bx.x, 1.5) && near(r.y, bx.y, 1.5), r);

  // --- 3. drag inside moves without resizing -------------------------------
  const before = await box();
  const c = P(before.x + before.w / 2, before.y + before.h / 2);
  await page.mouse.move(c.x, c.y); await page.mouse.down();
  await page.mouse.move(c.x + 60, c.y + 40); await page.mouse.up();
  r = await box();
  check('move: size unchanged', r && near(r.w, before.w, 0.5) && near(r.h, before.h, 0.5), r);
  check('move: position changed', r && (r.x > before.x && r.y > before.y), { before: before.x, after: r.x });

  // --- 4. numeric input: width drives height under lock --------------------
  await page.fill('#iw', '800');
  await page.press('#iw', 'Enter');
  r = await box();
  check('input W=800 applied', r && near(r.w, 800, 0.5), r && r.w);
  check('input: height derived by lock', r && near(r.h, 800 / R169, 0.5), r && r.h);
  check('H input disabled while locked', await page.evaluate(() => document.getElementById('ih').disabled));
  check('status shows ratio + norm', (await info()).ratio.includes('16:9') && (await info()).norm.includes('→'));

  // --- 5. arrow nudge: box mode -------------------------------------------
  // The numeric input above still owns focus; a text field must swallow arrows
  // by design, so verify that guard, then blur and test the nudge.
  const g0 = await box();
  await page.keyboard.press('ArrowRight');
  const g1 = await box();
  check('arrows ignored while typing in an input', near(g1.x, g0.x, 0.001), { before: g0.x, after: g1.x });
  const stillEditing = await page.evaluate(() => document.activeElement && document.activeElement.tagName);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const p0 = await box();
  await page.keyboard.press('ArrowRight');
  let p1 = await box();
  check('arrow: moves 1px', near(p1.x, p0.x + 1, 0.01), { focus: stillEditing, before: p0.x, after: p1.x });
  await page.keyboard.press('Shift+ArrowRight');
  let p2 = await box();
  check('shift+arrow: moves 10px', near(p2.x, p1.x + 10, 0.01), { before: p1.x, after: p2.x });

  // --- 6. arrow nudge: handle mode (select east handle by clicking it) -----
  const hb = await box();
  const eastPt = { x: hb.x + hb.w, y: hb.y + hb.h / 2 };
  const hitAt = await page.evaluate(pt => handleAt(pt), eastPt);
  const east = await page.evaluate(pt => {
    const k = S.view.k, r = document.getElementById('ov').getBoundingClientRect();
    return { x: r.left + pt.x * k, y: r.top + pt.y * k };
  }, eastPt);
  console.log('   [debug] handleAt(east)=%s  box=%s  screen=%s', hitAt, JSON.stringify(hb), JSON.stringify(east));
  await page.mouse.move(east.x, east.y);
  await page.mouse.down();
  const during = await page.evaluate(() => ({ handle: S.handle, mode: S.drag && S.drag.mode }));
  console.log('   [debug] after mousedown: %s', JSON.stringify(during));
  await page.mouse.up();
  check('handle selected', (await info()).target === '右边', { hitAt: hitAt, during: during, target: (await info()).target });
  const h0 = await box();
  await page.keyboard.press('ArrowRight');
  const h1 = await box();
  check('handle arrow: width +1 exactly', near(h1.w - h0.w, 1, 0.01), { w0: h0.w, w1: h1.w });
  check('handle arrow: ratio kept', near(h1.w / h1.h, R169), h1.w / h1.h);
  await page.keyboard.press('Escape');
  check('escape clears handle', (await info()).target !== '右边', (await info()).target);

  // --- 7. undo -------------------------------------------------------------
  await page.keyboard.press('Control+z');
  const u1 = await box();
  check('ctrl+z restores width', near(u1.w, h0.w, 0.01), { expected: h0.w, got: u1.w });

  // --- 8. zoom + pan + fit -------------------------------------------------
  const v0 = await view();
  await page.keyboard.down('Control');
  await page.mouse.move(geo.left + geo.iw * geo.k / 2, geo.top + geo.ih * geo.k / 2);
  await page.mouse.wheel(0, -120);
  await page.keyboard.up('Control');
  const v1 = await view();
  check('ctrl+wheel zooms in', v1.k > v0.k, { before: v0.k, after: v1.k });
  const stage = await page.evaluate(() => { const r = document.getElementById('stage').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.move(stage.x, stage.y);
  await page.mouse.down({ button: 'middle' });
  await page.mouse.move(stage.x + 40, stage.y + 30);
  await page.mouse.up({ button: 'middle' });
  const v2 = await view();
  check('middle-drag pans', !near(v2.tx, v1.tx, 0.01) || !near(v2.ty, v1.ty, 0.01), { v1: v1.tx, v2: v2.tx });
  await page.click('#fit');
  const v3 = await view();
  check('fit restores fit scale', v3.k !== v1.k, { zoomed: v1.k, fit: v3.k });

  // --- 9. switch to ellipse: is the ratio lock honoured? ------------------
  await page.click('#tEll');
  const e0 = P(300, 300), e1 = P(900, 560);
  await page.mouse.move(e0.x, e0.y); await page.mouse.down();
  await page.mouse.move(e1.x, e1.y); await page.mouse.up();
  const eb = await box();
  check('ellipse: ratio locked', eb && near(eb.w / eb.h, R169), eb && eb.w / eb.h);


  // --- 11. selections STACK: a new box must NOT clear the previous one -----
  // Start from a clean slate so item counts are deterministic (step 9 left an
  // ellipse behind on purpose - that is the stacking contract, not a bug).
  await page.click('#clear');
  const clearedCount = await page.evaluate(() => S.items.length);
  check('clear empties the list', clearedCount === 0, { count: clearedCount });
  await page.click('#tRect');
  const a1 = P(150, 150), b1 = P(500, 350);
  await page.mouse.move(a1.x, a1.y); await page.mouse.down(); await page.mouse.move(b1.x, b1.y); await page.mouse.up();
  const first = await box();
  const a2 = P(900, 500), b2 = P(1300, 700);
  await page.mouse.move(a2.x, a2.y); await page.mouse.down(); await page.mouse.move(b2.x, b2.y); await page.mouse.up();
  const second = await box();
  const firstStill = await page.evaluate(pt => {
    const s = sel.getContext('2d').getImageData(pt.x, pt.y, 1, 1).data[0];
    return s;               // 0 = still painted, 255 = cleared
  }, { x: Math.round(first.x + first.w / 2), y: Math.round(first.y + first.h / 2) });
  const count2 = await page.evaluate(() => S.items.length);
  check('stack: previous box kept', firstStill === 0, { first: first, firstR: firstStill });
  check('stack: two items coexist', count2 === 2, { count: count2 });
  check('stack: new box selected', (() => { const b = second; return b && Math.abs(b.w - first.w) > 1; })(), { first: first, second: second });

  // --- 12. list panel + click-select + delete-selected --------------------
  const listRows = await page.evaluate(() => document.querySelectorAll('#listBody .row').length);
  check('list panel shows both items', listRows === 2, { rows: listRows });
  await page.evaluate(() => document.querySelectorAll('#listBody .row .nm')[0].click());
  const selAfter = await page.evaluate(() => S.selId);
  const firstId = await page.evaluate(() => S.items[0].id);
  check('list click selects that item', selAfter === firstId, { selAfter: selAfter, firstId: firstId });
  await page.click('#delSel');
  const countAfterDel = await page.evaluate(() => S.items.length);
  const leftCenter = await page.evaluate(pt => {
    const s = sel.getContext('2d').getImageData(pt.x, pt.y, 1, 1).data[0];
    return s;
  }, { x: Math.round(first.x + first.w / 2), y: Math.round(first.y + first.h / 2) });
  check('delete-selected removes exactly one', countAfterDel === 1, { count: countAfterDel });
  check('delete-selected clears its pixels', leftCenter === 255, { r: leftCenter });
  check('other item survives the delete', await page.evaluate(() => S.items.length === 1));

  // --- 13. delete via keyboard (Delete) on the remaining item -------------
  await page.evaluate(() => { S.selId = S.items[0].id; });
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('Delete');
  check('Delete key removes the item', await page.evaluate(() => S.items.length === 0));

  // --- 14. brush strokes are themselves removable selections --------------
  await page.click('#tBrush');
  const s0 = P(300, 300), s1 = P(420, 380);
  await page.mouse.move(s0.x, s0.y); await page.mouse.down();
  await page.mouse.move(s1.x, s1.y); await page.mouse.up();
  const brushCount = await page.evaluate(() => S.items.filter(i => i.kind === 'brush').length);
  check('brush creates a removable item', brushCount === 1, { brushCount: brushCount });
  // Regression: the brush must also paint while a SHAPE item is selected and
  // already on the canvas (a stale page or an accidental select must not block it).
  await page.click('#tRect');
  const rb0 = P(600, 600), rb1 = P(680, 660);
  await page.mouse.move(rb0.x, rb0.y); await page.mouse.down(); await page.mouse.move(rb1.x, rb1.y); await page.mouse.up();
  await page.click('#tBrush');
  const nBefore = await page.evaluate(() => S.items.length);
  const st0 = P(900, 700), st1 = P(980, 760);
  await page.mouse.move(st0.x, st0.y); await page.mouse.down();
  await page.mouse.move(st1.x, st1.y); await page.mouse.up();
  const nAfter = await page.evaluate(() => S.items.length);
  check('brush paints even with a shape selected', nAfter === nBefore + 1, { before: nBefore, after: nAfter });
  check('brush stroke recorded', await page.evaluate(() => S.items.some(i => i.kind === 'brush' && i.strokes.length >= 2)));

  // --- 15. an ERASER stroke is also a selectable item (regression) --------
  // It used to be invisible to shapeAt(), so no tool could select it.
  await page.click('#tEraser');
  const er0 = P(700, 400), er1 = P(760, 430);
  await page.mouse.move(er0.x, er0.y); await page.mouse.down();
  await page.mouse.move(er1.x, er1.y); await page.mouse.up();
  const eraserId = await page.evaluate(() => (S.items.find(i => i.kind === 'eraser') || {}).id);
  check('eraser creates an item', eraserId !== undefined, { eraserId: eraserId });
  // Select it while a SHAPE tool is active (that path always consults shapeAt),
  // clicking a point that is genuinely ON the stroke (not its midpoint).
  await page.click('#tRect');
  await page.evaluate(() => { S.selId = null; });
  const erPt = await page.evaluate(id => {
    const it = S.items.find(i => i.id === id);
    const s = it.strokes[it.strokes.length - 1];
    return { x: s.x, y: s.y };
  }, eraserId);
  const hitOn = P(erPt.x, erPt.y);
  await page.mouse.click(hitOn.x, hitOn.y);
  check('clicking an eraser stroke selects it', await page.evaluate(id => S.selId === id, eraserId),
        { selId: await page.evaluate(() => S.selId), want: eraserId });
  // selecting the eraser must not crash the status panel
  check('eraser status shows stroke count', (await info()).size.includes('点'), (await info()).size);

  // --- 16. Alt+click while a brush is active picks the shape --------------
  await page.click('#tBrush');
  await page.evaluate(() => { S.selId = null; });
  const itemsBeforeAlt = await page.evaluate(() => S.items.length);
  const altPt = P(erPt.x, erPt.y);
  await page.keyboard.down('Alt');
  await page.mouse.click(altPt.x, altPt.y);
  await page.keyboard.up('Alt');
  const itemsAfterAlt = await page.evaluate(() => S.items.length);
  check('Alt+click selects instead of painting', await page.evaluate(id => S.selId === id, eraserId),
        { selId: await page.evaluate(() => S.selId), want: eraserId, items: itemsAfterAlt });
  check('Alt+click did not add a stroke item', itemsAfterAlt === itemsBeforeAlt,
        { before: itemsBeforeAlt, after: itemsAfterAlt });

  // --- 17. undo walks back more than one step ----------------------------
  // Currently: [rect?, brush, eraser]. Delete twice, then undo twice.
  const before17 = await page.evaluate(() => S.items.length);
  await page.evaluate(() => { S.selId = S.items[S.items.length - 1].id; });
  await page.click('#delSel');
  const after1 = await page.evaluate(() => S.items.length);
  await page.evaluate(() => { if (S.items.length) S.selId = S.items[S.items.length - 1].id; });
  await page.click('#delSel');
  const after2 = await page.evaluate(() => S.items.length);
  await page.keyboard.press('Control+z');
  const undo1 = await page.evaluate(() => S.items.length);
  await page.keyboard.press('Control+z');
  const undo2 = await page.evaluate(() => S.items.length);
  check('two deletes shrink the list by two', after1 === before17 - 1 && after2 === before17 - 2,
        { before17: before17, after1: after1, after2: after2 });
  check('ctrl+z undoes deletion step 1', undo1 === after2 + 1, { undo1: undo1, after2: after2 });
  check('ctrl+z undoes deletion step 2', undo2 === before17, { undo2: undo2, before17: before17 });

  // --- 18. the list panel tracks a live resize (regression) ---------------
  // setBox() used to skip the list, so a handle drag left stale W×H text.
  await page.click('#clear');
  await page.click('#tRect');
  const L0 = P(200, 200), L1 = P(500, 350);
  await page.mouse.move(L0.x, L0.y); await page.mouse.down(); await page.mouse.move(L1.x, L1.y); await page.mouse.up();
  const labelBefore = await page.evaluate(() => document.querySelector('#listBody .row .nm').textContent);
  const bx18 = await box();
  const se18 = P(bx18.x + bx18.w, bx18.y + bx18.h);
  await page.mouse.move(se18.x, se18.y); await page.mouse.down();
  await page.mouse.move(se18.x + 120, se18.y + 120);   // still holding: mid-drag
  const labelDuring = await page.evaluate(() => document.querySelector('#listBody .row .nm').textContent);
  await page.mouse.up();
  const labelAfter = await page.evaluate(() => document.querySelector('#listBody .row .nm').textContent);
  check('list label updates mid-drag', labelDuring !== labelBefore, { before: labelBefore, during: labelDuring });
  const cur = await box();
  const curId = await page.evaluate(() => S.selId);
  check('list label matches the new size',
        labelAfter === '#' + curId + ' · 矩形 ' + Math.round(cur.w) + '×' + Math.round(cur.h),
        { after: labelAfter, want: '#' + curId + ' · 矩形 ' + Math.round(cur.w) + '×' + Math.round(cur.h) });

  // --- 19. polygon tool: click points, close, becomes a selection ---------
  await page.click('#clear');
  await page.click('#tPoly');
  const poly = [P(300, 300), P(600, 320), P(640, 560), P(280, 520)];
  for (const pt of poly) { await page.mouse.click(pt.x, pt.y); }
  const draftPts = await page.evaluate(() => (S.draft ? S.draft.points.length : 0));
  check('polygon collects clicked points', draftPts === 4, { points: draftPts });
  // close by clicking back on the first vertex
  await page.mouse.click(poly[0].x, poly[0].y);
  const polyItem = await page.evaluate(() => S.items.find(i => i.kind === 'poly'));
  check('polygon closes into an item', !!polyItem && polyItem.points.length === 4,
        { item: polyItem ? polyItem.points.length : null });
  check('polygon is selected after closing', await page.evaluate(() => S.selId !== null));
  const insidePt = P(450, 400);
  const polySel = await page.evaluate(pt => { const h = shapeAt(pt); return h ? h.kind : null; }, { x: 450, y: 400 });
  const polyOut = await page.evaluate(pt => { const h = shapeAt(pt); return h ? h.kind : null; }, { x: 1000, y: 800 });
  check('point inside polygon hits it', polySel === 'poly', { hit: polySel });
  check('point outside polygon misses it', polyOut !== 'poly', { hit: polyOut });
  // the mask bitmap must carry the polygon fill
  const polyFilled = await page.evaluate(pt => sel.getContext('2d').getImageData(pt.x, pt.y, 1, 1).data[0], { x: 450, y: 400 });
  check('polygon is filled into the mask', polyFilled === 0, { r: polyFilled });

  // --- 20. polygon: Backspace drops the last point, Esc cancels -----------
  await page.click('#tPoly');
  await page.mouse.click(P(400, 400).x, P(400, 400).y);
  await page.mouse.click(P(500, 400).x, P(500, 400).y);
  await page.mouse.click(P(500, 500).x, P(500, 500).y);
  await page.keyboard.press('Backspace');
  const afterBs = await page.evaluate(() => (S.draft ? S.draft.points.length : -1));
  check('Backspace drops the last polygon point', afterBs === 2, { points: afterBs });
  await page.keyboard.press('Escape');
  check('Escape cancels the polygon draft', await page.evaluate(() => S.draft === null));

  // --- 21. brush strokes are continuous, not disconnected dots ------------
  // Regression: sparse samples used to render as separate circles.
  await page.click('#tBrush');
  const c0 = P(200, 800), c1 = P(700, 850);
  await page.mouse.move(c0.x, c0.y); await page.mouse.down();
  for (let i = 1; i <= 5; i++) {
    await page.mouse.move(c0.x + (c1.x - c0.x) * i / 5, c0.y + (c1.y - c0.y) * i / 5);
  }
  await page.mouse.up();
  const brushInfo = await page.evaluate(() => {
    const it = S.items.filter(i => i.kind === 'brush').slice(-1)[0];
    const p0 = it.strokes[0], p1 = it.strokes[1];
    const mx = Math.round((p0.x + p1.x) / 2), my = Math.round((p0.y + p1.y) / 2);
    return {
      samples: it.strokes.length,
      midPixel: sel.getContext('2d').getImageData(mx, my, 1, 1).data[0],
    };
  });
  check('brush records multiple samples', brushInfo.samples >= 2, brushInfo);
  check('brush stroke is continuous between samples', brushInfo.midPixel === 0, brushInfo);

  // --- 22. the brush OUTLINE is a connected path, not a string of rings -----
  // Regression: outlineItem() drew one circle per sample, which users described
  // as "only ever seeing circles" even though the fill underneath was solid.
  const outlineInfo = await page.evaluate(() => {
    const it = S.items.filter(i => i.kind === 'brush').slice(-1)[0];
    S.selId = it.id;
    render();
    const p0 = it.strokes[0], p1 = it.strokes[1];
    const k = S.view.k;
    // A point midway between the two samples (so no ring would sit there) but
    // within the stroke's width: a connected outline paints it, rings do not.
    const mx = Math.round((p0.x + p1.x) / 2 * k);
    const my = Math.round((p0.y + p1.y) / 2 * k);
    const d = ov.getContext('2d').getImageData(mx, my, 1, 1).data;
    return { alpha: d[3] };
  });
  check('brush outline runs continuously along the stroke', outlineInfo.alpha > 0, outlineInfo);

  // --- 10. save ------------------------------------------------------------
  await page.click('#save');
  await page.waitForTimeout(2500);
  check('mask written to disk', fs.existsSync(MASK), MASK);
  check('no page errors', pageErrors.length === 0, pageErrors.slice(0, 3));

  console.log('fails = ' + fails.length + (fails.length ? ' ' + JSON.stringify(fails) : ''));
  await browser.close();
  process.exit(fails.length ? 1 : 0);
})().catch(err => { console.log('E2E CRASH: ' + err); process.exit(2); });
