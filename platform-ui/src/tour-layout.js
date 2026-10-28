/** Geometry stays independent of the DOM so viewport edge cases can be tested. */
function rectangle(value) {
  if (!value) return null;
  const left = Number(value.left);
  const top = Number(value.top);
  const right = Number(value.right ?? left + Number(value.width));
  const bottom = Number(value.bottom ?? top + Number(value.height));
  if (![left, top, right, bottom].every(Number.isFinite) || right <= left || bottom <= top) return null;
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

export function clipTourTargetRect(target, clippingRects = []) {
  let result = rectangle(target);
  if (!result) return null;
  for (const clip of clippingRects) {
    const bounds = rectangle(clip);
    if (!bounds) return null;
    result = rectangle({
      left: Math.max(result.left, bounds.left),
      top: Math.max(result.top, bounds.top),
      right: Math.min(result.right, bounds.right),
      bottom: Math.min(result.bottom, bounds.bottom),
    });
    if (!result) return null;
  }
  return result;
}

const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(value, maximum));

/** All returned coordinates are relative to the visible viewport, including zoom. */
export function getTourLayout({ viewport, targetRect, tooltip, gutter = 12, gap = 14, spotlightPadding = 6 }) {
  const viewportWidth = Math.max(1, Number(viewport?.width) || 1);
  const viewportHeight = Math.max(1, Number(viewport?.height) || 1);
  const margin = Math.min(gutter, viewportWidth / 4, viewportHeight / 4);
  const width = Math.min(Math.max(1, Number(tooltip?.width) || 360), viewportWidth - margin * 2);
  const height = Math.min(Math.max(1, Number(tooltip?.height) || 240), viewportHeight - margin * 2);
  const mobile = viewportWidth <= 640;
  const visibleTarget = clipTourTargetRect(targetRect, [{ left: 0, top: 0, width: viewportWidth, height: viewportHeight }]);
  const spotlight = visibleTarget ? rectangle({
    left: Math.max(0, visibleTarget.left - spotlightPadding),
    top: Math.max(0, visibleTarget.top - spotlightPadding),
    right: Math.min(viewportWidth, visibleTarget.right + spotlightPadding),
    bottom: Math.min(viewportHeight, visibleTarget.bottom + spotlightPadding),
  }) : null;
  const fit = (candidate) => ({
    ...candidate,
    left: clamp(candidate.left, margin, viewportWidth - margin - width),
    top: clamp(candidate.top, margin, viewportHeight - margin - height),
  });
  if (!spotlight) {
    return {
      ...fit({ left: (viewportWidth - width) / 2, top: mobile ? viewportHeight - margin - height : (viewportHeight - height) / 2 }),
      width, height, placement: "fallback", spotlight: null, overlapsTarget: false,
    };
  }
  const centeredLeft = (spotlight.left + spotlight.right - width) / 2;
  const centeredTop = (spotlight.top + spotlight.bottom - height) / 2;
  const candidates = [
    { left: centeredLeft, top: spotlight.bottom + gap, placement: "below" },
    { left: centeredLeft, top: spotlight.top - gap - height, placement: "above" },
    ...(!mobile ? [
      { left: spotlight.right + gap, top: centeredTop, placement: "right" },
      { left: spotlight.left - gap - width, top: centeredTop, placement: "left" },
    ] : []),
  ];
  const fits = candidates.find((candidate) => candidate.left >= margin && candidate.top >= margin
    && candidate.left + width <= viewportWidth - margin && candidate.top + height <= viewportHeight - margin);
  // Horizontal centering may need clamping even when a vertical placement fits.
  const verticalFit = candidates.slice(0, 2).find((candidate) => candidate.top >= margin && candidate.top + height <= viewportHeight - margin);
  let selected = fits || verticalFit;
  if (!selected) {
    const overlap = (candidate) => Math.max(0, Math.min(candidate.left + width, spotlight.right) - Math.max(candidate.left, spotlight.left))
      * Math.max(0, Math.min(candidate.top + height, spotlight.bottom) - Math.max(candidate.top, spotlight.top));
    selected = candidates.map(fit).reduce((best, candidate) => overlap(candidate) < overlap(best) ? candidate : best);
  }
  selected = fit(selected);
  const overlapsTarget = selected.left < spotlight.right && selected.left + width > spotlight.left
    && selected.top < spotlight.bottom && selected.top + height > spotlight.top;
  return { ...selected, width, height, spotlight, overlapsTarget };
}
