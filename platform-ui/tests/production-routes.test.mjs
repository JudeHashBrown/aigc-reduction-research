import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const app = readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
const core = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");
const operations = readFileSync(fileURLToPath(new URL("../src/pages/OperationsPages.jsx", import.meta.url)), "utf8");

test("production navigation has no prototype sitemap or demo system routes", () => {
  assert.doesNotMatch(app, /PageMap|pageGroups|SITE MAP|local MVP|rt-map-fab/);
  assert.doesNotMatch(app, /"\/(?:500|offline|maintenance|session-expired|insufficient-balance)"/);
  assert.doesNotMatch(operations.slice(operations.indexOf("export function SystemStatePage")), /RT-DEMO|CONNECTION LOST|PLANNED MAINTENANCE/);
});

test("document navigation uses a semantic route and preserves old bookmarks", () => {
  assert.match(app, /"\/app\/workbench": WorkbenchPage/);
  assert.match(app, /"\/app\/documents\/rt-014": "\/app\/workbench"/);
  assert.doesNotMatch(core, /\/app\/documents\/rt-014/);
});
