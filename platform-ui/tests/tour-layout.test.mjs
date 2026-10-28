import assert from "node:assert/strict";
import { test } from "node:test";
import { clipTourTargetRect, getTourLayout } from "../src/tour-layout.js";

const viewport = { width: 1280, height: 800 };
const tooltip = { width: 360, height: 240 };

function assertFits(layout, bounds) {
  assert.ok(layout.left >= 0 && layout.top >= 0);
  assert.ok(layout.left + layout.width <= bounds.width);
  assert.ok(layout.top + layout.height <= bounds.height);
}

test("clipping a nested scroll target highlights only its visible intersection", () => {
  const visible = clipTourTargetRect({ left: 40, top: 100, width: 800, height: 900 }, [
    { left: 0, top: 0, width: 1024, height: 768 },
    { left: 60, top: 180, width: 600, height: 360 },
  ]);
  assert.deepEqual(visible, { left: 60, top: 180, right: 660, bottom: 540, width: 600, height: 360 });
});

test("missing, invalid, hidden, or fully clipped targets produce no spotlight", () => {
  assert.equal(clipTourTargetRect(null), null);
  assert.equal(clipTourTargetRect({ left: 0, top: 0, width: 0, height: 20 }), null);
  assert.equal(clipTourTargetRect({ left: NaN, top: 0, width: 20, height: 20 }), null);
  const layout = getTourLayout({ viewport, tooltip, targetRect: { left: 0, top: -200, width: 20, height: 100 } });
  assert.equal(layout.spotlight, null);
  assert.equal(layout.placement, "fallback");
  assertFits(layout, viewport);
});

test("a regular target gets a contextual panel below it without overlap", () => {
  const layout = getTourLayout({ viewport, tooltip, targetRect: { left: 500, top: 100, width: 180, height: 80 } });
  assert.equal(layout.placement, "below");
  assert.equal(layout.top, 200);
  assert.equal(layout.overlapsTarget, false);
  assertFits(layout, viewport);
});

test("a target near the viewport bottom puts the panel above it", () => {
  const layout = getTourLayout({ viewport, tooltip, targetRect: { left: 400, top: 700, width: 160, height: 60 } });
  assert.equal(layout.placement, "above");
  assert.equal(layout.overlapsTarget, false);
  assertFits(layout, viewport);
});

test("a tall narrow target uses side space when neither vertical side fits", () => {
  const layout = getTourLayout({ viewport, tooltip, targetRect: { left: 100, top: 50, width: 200, height: 700 } });
  assert.equal(layout.placement, "right");
  assert.equal(layout.overlapsTarget, false);
  assertFits(layout, viewport);
});

test("mobile panels respect their measured size and remain within the viewport", () => {
  const bounds = { width: 320, height: 640 };
  const layout = getTourLayout({ viewport: bounds, tooltip: { width: 296, height: 286 }, targetRect: { left: 8, top: 25, width: 304, height: 40 } });
  assert.equal(layout.left, 12);
  assert.equal(layout.width, 296);
  assert.equal(layout.height, 286);
  assert.equal(layout.overlapsTarget, false);
  assertFits(layout, bounds);
});

test("a large target and a tall mobile tooltip still leave navigation on screen", () => {
  const bounds = { width: 375, height: 667 };
  const layout = getTourLayout({ viewport: bounds, tooltip: { width: 351, height: 450 }, targetRect: { left: -40, top: -80, width: 700, height: 1200 } });
  assertFits(layout, bounds);
  assert.deepEqual(layout.spotlight, { left: 0, top: 0, right: 375, bottom: 667, width: 375, height: 667 });
  assert.equal(layout.overlapsTarget, true);
});

test("oversized tooltips and short visual viewports are clamped in both axes", () => {
  for (const bounds of [{ width: 320, height: 220 }, { width: 180, height: 120 }, { width: 20, height: 20 }]) {
    const layout = getTourLayout({ viewport: bounds, tooltip: { width: 600, height: 800 }, targetRect: { left: 0, top: 0, width: 80, height: 70 } });
    assertFits(layout, bounds);
    assert.ok(layout.width > 0 && layout.height > 0);
  }
});

test("targets near either horizontal edge never push the panel offscreen", () => {
  for (const left of [-20, 0, 1250]) {
    const layout = getTourLayout({ viewport, tooltip, targetRect: { left, top: 50, width: 80, height: 80 } });
    assertFits(layout, viewport);
    assert.equal(layout.overlapsTarget, false);
  }
});
