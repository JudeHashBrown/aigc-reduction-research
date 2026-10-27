import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const app = readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
const workbench = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");

test("the top-right AI readiness badge is absent while the service-status route remains", () => {
  assert.doesNotMatch(app, /rt-status-button|AI service ready|AI 服务已就绪/);
  assert.doesNotMatch(workbench, /AI ready|AI 服务已就绪/);
  assert.match(app, /"\/app\/settings\/service": ServiceStatusPage/);
});
