import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const app = readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
const css = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");

test("mobile account controls remain available and all admin destinations fit in visible navigation", () => {
  assert.match(app, /isAdmin && <button role="menuitem" onClick=\{\(\) => navigate\("\/app"\)\}/);
  assert.match(app, /rt-sidebar--admin/);
  assert.match(css, /\.rt-sidebar--admin nav\s*\{[^}]*grid-template-columns:\s*repeat\(5, minmax\(0, 1fr\)\);[^}]*grid-template-rows:\s*repeat\(2, 54px\);/);
  assert.doesNotMatch(css, /\.rt-balance,\s*\.rt-user-button\s*\{\s*display:\s*none;/);
});
