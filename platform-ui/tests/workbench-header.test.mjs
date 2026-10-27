import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const workbench = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");
const styles = readFileSync(fileURLToPath(new URL("../src/pages/live-core-pages.css", import.meta.url)), "utf8");

test("the document return action is a visible, accessible button", () => {
  assert.match(workbench, /<button type="button" className="rt-doc-back" onClick=\{\(\) => navigate\("\/app"\)\}>/);
  assert.match(workbench, /<ArrowLeft size=\{18\} weight="bold" aria-hidden="true" \/>/);
  assert.match(workbench, /Back to documents" : "返回文档/);
  assert.match(styles, /\.rt-live-workbench \.rt-doc-back \{[^}]*min-height: 42px;[^}]*border: 2px solid var\(--rt-ink\);[^}]*box-shadow: 3px 3px 0 var\(--rt-ink\);/s);
  assert.match(styles, /\.rt-live-workbench \.rt-doc-back:focus-visible \{/);
});
