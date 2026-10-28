import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { clipTourTargetRect, getTourLayout } from "./tour-layout.js";
import "./guided-tour.css";

function visibleViewport() {
  const viewport = window.visualViewport;
  return {
    left: viewport?.offsetLeft || 0,
    top: viewport?.offsetTop || 0,
    width: viewport?.width || document.documentElement.clientWidth || window.innerWidth,
    height: viewport?.height || window.innerHeight,
  };
}

function visibleElement(selector) {
  if (!selector) return null;
  let matches;
  try { matches = document.querySelectorAll(selector); } catch { return null; }
  return Array.from(matches).find((element) => {
    const rect = element.getBoundingClientRect();
    if (!element.getClientRects().length || rect.width <= 0 || rect.height <= 0) return false;
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const style = window.getComputedStyle(ancestor);
      if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse"
        || style.contentVisibility === "hidden" || Number(style.opacity) === 0) return false;
    }
    return true;
  }) || null;
}

function targetInViewport(element, viewport) {
  if (!element) return null;
  const clipping = [{ left: viewport.left, top: viewport.top, width: viewport.width, height: viewport.height }];
  for (let ancestor = element.parentElement; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
    const style = window.getComputedStyle(ancestor);
    const clipsX = /auto|scroll|hidden|clip|overlay/.test(style.overflowX);
    const clipsY = /auto|scroll|hidden|clip|overlay/.test(style.overflowY);
    if (!clipsX && !clipsY) continue;
    const rect = ancestor.getBoundingClientRect();
    const scaleX = ancestor.offsetWidth ? rect.width / ancestor.offsetWidth : 1;
    const scaleY = ancestor.offsetHeight ? rect.height / ancestor.offsetHeight : 1;
    const left = rect.left + ancestor.clientLeft * scaleX;
    const top = rect.top + ancestor.clientTop * scaleY;
    clipping.push({
      left: clipsX ? left : viewport.left,
      top: clipsY ? top : viewport.top,
      right: clipsX ? left + ancestor.clientWidth * scaleX : viewport.left + viewport.width,
      bottom: clipsY ? top + ancestor.clientHeight * scaleY : viewport.top + viewport.height,
    });
  }
  const rect = clipTourTargetRect(element.getBoundingClientRect(), clipping);
  return rect ? { left: rect.left - viewport.left, top: rect.top - viewport.top, width: rect.width, height: rect.height } : null;
}

const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** A read-only tour: targets are measured and scrolled, never activated. */
export function GuidedTour({ steps = [], isEnglish = false, onExit }) {
  const [index, setIndex] = useState(0);
  const [geometry, setGeometry] = useState(null);
  const panelRef = useRef(null);
  const exitRef = useRef(onExit);
  const closedRef = useRef(false);
  const id = useId();
  const currentIndex = Math.min(index, Math.max(steps.length - 1, 0));
  const step = steps[currentIndex];
  exitRef.current = onExit;
  const exit = (reason) => {
    if (closedRef.current) return;
    closedRef.current = true;
    exitRef.current?.(reason);
  };

  useEffect(() => { if (!steps.length) exit("completed"); }, [steps.length]);

  useLayoutEffect(() => {
    if (!step || typeof document === "undefined") return undefined;
    const previousFocus = document.activeElement;
    const root = document.getElementById("root");
    const rootAttributes = root ? { inert: root.getAttribute("inert"), ariaHidden: root.getAttribute("aria-hidden") } : null;
    // Move focus before hiding its previous ancestor from assistive technology.
    panelRef.current?.focus({ preventScroll: true });
    if (root) { root.setAttribute("inert", ""); root.setAttribute("aria-hidden", "true"); }
    const focusable = () => Array.from(panelRef.current?.querySelectorAll(focusableSelector) || [])
      .filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0 && window.getComputedStyle(element).visibility !== "hidden");
    const onKeyDown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); exit("skipped"); }
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0];
      const last = controls.at(-1);
      if (!first) { event.preventDefault(); panelRef.current?.focus({ preventScroll: true }); return; }
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !controls.includes(active))) {
        event.preventDefault(); last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (active === last || !controls.includes(active))) {
        event.preventDefault(); first.focus({ preventScroll: true });
      }
    };
    const onFocus = (event) => {
      if (panelRef.current && !panelRef.current.contains(event.target)) panelRef.current.focus({ preventScroll: true });
    };
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocus, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocus, true);
      if (root && rootAttributes) {
        for (const [attribute, value] of [["inert", rootAttributes.inert], ["aria-hidden", rootAttributes.ariaHidden]]) {
          if (value === null) root.removeAttribute(attribute); else root.setAttribute(attribute, value);
        }
      }
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [Boolean(step)]);

  useLayoutEffect(() => {
    if (!step || typeof document === "undefined") return undefined;
    let frame = 0;
    let observedTarget = null;
    let resizeObserver;
    const measure = () => {
      frame = 0;
      const viewport = visibleViewport();
      const target = visibleElement(step.target);
      if (target !== observedTarget) {
        if (observedTarget) resizeObserver?.unobserve(observedTarget);
        if (target) resizeObserver?.observe(target);
        observedTarget = target;
      }
      const tooltip = panelRef.current?.getBoundingClientRect();
      const layout = getTourLayout({ viewport, targetRect: targetInViewport(target, viewport), tooltip });
      const next = { viewport, layout };
      setGeometry((previous) => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(measure); };
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(schedule);
      if (panelRef.current) resizeObserver.observe(panelRef.current);
      if (document.getElementById("root")) resizeObserver.observe(document.getElementById("root"));
    }
    const target = visibleElement(step.target);
    // Jump before measuring so the navigation controls do not move under a
    // pointer while a previous smooth scroll is still in progress.
    target?.scrollIntoView({ behavior: "instant", block: "center", inline: "nearest" });
    measure();
    panelRef.current?.focus({ preventScroll: true });
    window.addEventListener("resize", schedule);
    // Capture catches scrolls from nested editor panels as well as the document.
    document.addEventListener("scroll", schedule, true);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    const mutationObserver = new MutationObserver(schedule);
    const root = document.getElementById("root");
    if (root) mutationObserver.observe(root, { subtree: true, childList: true, attributes: true });
    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      mutationObserver.disconnect();
      window.removeEventListener("resize", schedule);
      document.removeEventListener("scroll", schedule, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
    };
  }, [currentIndex, step?.target, step?.title, step?.description, isEnglish]);

  if (!step || typeof document === "undefined") return null;
  const viewport = geometry?.viewport || visibleViewport();
  const layout = geometry?.layout;
  const spotlight = layout?.spotlight;
  const shadePath = `M0 0H${viewport.width}V${viewport.height}H0Z${spotlight ? ` M${spotlight.left} ${spotlight.top}H${spotlight.right}V${spotlight.bottom}H${spotlight.left}Z` : ""}`;
  const stopPropagation = (event) => event.stopPropagation();
  return createPortal(<div className="rt-guided-tour" style={{ left: viewport.left, top: viewport.top, width: viewport.width, height: viewport.height }}
    onClick={stopPropagation} onPointerDown={stopPropagation} onKeyDown={stopPropagation}>
    <svg className="rt-guided-tour__shade" width={viewport.width} height={viewport.height} viewBox={`0 0 ${viewport.width} ${viewport.height}`} aria-hidden="true">
      <path d={shadePath} fillRule="evenodd" />
    </svg>
    {spotlight && <div className="rt-guided-tour__spotlight" aria-hidden="true" style={{ left: spotlight.left, top: spotlight.top, width: spotlight.width, height: spotlight.height }} />}
    <section ref={panelRef} className="rt-guided-tour__panel" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} tabIndex={-1}
      data-placement={layout?.placement || "fallback"} style={{ left: layout?.left ?? 12, top: layout?.top ?? 12, width: Math.max(1, Math.min(360, viewport.width - 24)), maxHeight: Math.max(1, viewport.height - 24), opacity: layout ? 1 : 0 }}>
      <div className="rt-guided-tour__topline">
        <span className="rt-guided-tour__progress">{isEnglish ? `Step ${currentIndex + 1} of ${steps.length}` : `第 ${currentIndex + 1} 步，共 ${steps.length} 步`}</span>
        <button type="button" className="rt-guided-tour__skip" onClick={() => exit("skipped")}>{isEnglish ? "Skip tour" : "跳过引导"}</button>
      </div>
      <div className="rt-guided-tour__copy" aria-live="polite" aria-atomic="true">
        <h2 id={`${id}-title`}>{step.title}</h2>
        <p id={`${id}-description`}>{step.description}</p>
      </div>
      <div className="rt-guided-tour__footer">
        <div className="rt-guided-tour__dots" aria-hidden="true">{steps.map((_, dot) => <span key={dot} className={dot === currentIndex ? "is-current" : ""} />)}</div>
        <div className="rt-guided-tour__actions">
          <button type="button" className="rt-guided-tour__back" disabled={currentIndex === 0} onClick={() => setIndex(currentIndex - 1)}>{isEnglish ? "Back" : "上一步"}</button>
          <button type="button" className="rt-guided-tour__next" onClick={() => currentIndex === steps.length - 1 ? exit("completed") : setIndex(currentIndex + 1)}>
            {currentIndex === steps.length - 1 ? (isEnglish ? "Finish" : "完成引导") : (isEnglish ? "Next" : "下一步")}<span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
    </section>
  </div>, document.body);
}
