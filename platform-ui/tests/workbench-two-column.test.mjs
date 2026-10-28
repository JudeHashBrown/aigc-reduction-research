import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pages = readFileSync(new URL("../src/pages/LiveCorePages.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/pages/live-core-pages.css", import.meta.url), "utf8");
const publicPages = readFileSync(new URL("../src/pages/PublicPages.jsx", import.meta.url), "utf8");
const publicStyles = readFileSync(new URL("../src/pages/public-pages.css", import.meta.url), "utf8");
const workbench = pages.split("export function WorkbenchPage(")[1]?.split("export function VersionsPage(")[0];
const versions = pages.split("export function VersionsPage(")[1];

test("live workbench puts its editable draft before diagnosis without a duplicate read-only source pane", () => {
  assert.ok(workbench, "WorkbenchPage must exist");
  const grid = workbench.split('<div className="rt-live-editor-grid">')[1]?.split("{lastResult && changeRows.length > 0")[0];
  assert.ok(grid, "live editor grid must exist");
  const currentIndex = grid.indexOf('<section className="rt-paper-panel is-current rt-live-editor-panel">');
  const findingsIndex = grid.indexOf('<aside className="rt-findings-panel rt-live-findings">');
  assert.ok(currentIndex >= 0 && findingsIndex > currentIndex, "editable draft should be the first panel");
  assert.doesNotMatch(grid, /Original manuscript|原始稿件|只读原稿|readOnly aria-label=/);
  assert.match(grid, /<textarea id="rt-current-editor"[^>]*value=\{current\}[^>]*onChange=\{\(event\) => editCurrent\(event\.target\.value\)\}/);
});

test("focus view retains the editable first panel and only hides diagnosis", () => {
  assert.match(styles, /\.rt-live-workbench\.is-focus-mode \.rt-live-editor-grid \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(styles, /\.rt-live-workbench\.is-focus-mode \.rt-live-findings \{ display: none; \}/);
  assert.doesNotMatch(styles, /\.rt-live-workbench\.is-focus-mode \.rt-live-editor-grid > :first-child/);
});

test("live editor uses two columns on desktop and one on smaller viewports", () => {
  const desktopColumns = styles.match(/\.rt-live-editor-grid \{\s*display: grid;\s*grid-template-columns: ([^;]+);/)?.[1];
  assert.ok(desktopColumns, "desktop columns must be declared");
  assert.equal((desktopColumns.match(/minmax\(/g) || []).length, 2);
  assert.match(styles, /@media \(max-width: 1180px\) \{\s*\.rt-live-editor-grid \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});

test("hiding the source pane does not erase source state or version restoration", () => {
  assert.match(workbench, /const \[source\] = useState\(initial\.source \|\| ""\)/);
  assert.match(workbench, /const \[current, setCurrent\] = useState\(initial\.current \|\| initial\.source \|\| ""\)/);
  assert.ok(versions, "VersionsPage must exist");
  assert.match(versions, /const restoreOriginal = async \(\) => \{/);
  assert.match(versions, /updateWorkspace\(\{ current: current\.source, report: null \}\)/);
  assert.match(versions, /Original import" : "原始导入"/);
  assert.match(versions, /Restore original" : "恢复原稿"/);
});

test("public workspace preview no longer advertises or renders a duplicate original pane", () => {
  assert.doesNotMatch(publicPages, /Original text, revised text, and evidence appear side by side|原稿、改稿和证据并排呈现/);
  const preview = publicPages.split("function WorkbenchPreview(")[1]?.split("export function LandingPage(")[0];
  assert.ok(preview, "public workbench preview must exist");
  assert.doesNotMatch(preview, /Original draft|原始稿件/);
  assert.match(preview, /'Current draft' : '当前稿件'/);
  assert.match(preview, /'Analysis & evidence' : '分析结果与证据'/);
  assert.match(publicStyles, /\.rtp-preview-grid \{[^}]*grid-template-columns: minmax\(0, 1\.2fr\) minmax\(0, 1fr\)/);
});
