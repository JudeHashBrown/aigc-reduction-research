import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const app = readFileSync(fileURLToPath(new URL("../src/App.jsx", import.meta.url)), "utf8");
const core = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");
const operations = readFileSync(fileURLToPath(new URL("../src/pages/OperationsPages.jsx", import.meta.url)), "utf8");
const publicPages = readFileSync(fileURLToPath(new URL("../src/pages/PublicPages.jsx", import.meta.url)), "utf8");
const auth = readFileSync(fileURLToPath(new URL("../src/pages/AuthPage.jsx", import.meta.url)), "utf8");

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

test("account data actions live in account settings and old privacy bookmarks redirect", () => {
  assert.match(app, /"\/app\/settings\/privacy": "\/app\/settings\/account"/);
  assert.doesNotMatch(app, /"\/app\/settings\/privacy": PrivacySettingsPage/);
  assert.match(operations, /<AccountDataControls email=\{user\.email \|\| ""\} navigate=\{navigate\} \/>/);
  assert.match(operations, /getApi\("\/api\/account\/data-export"\)/);
  assert.match(operations, /postApi\("\/api\/account\/delete-request"/);
});

test("public legal and help copy does not describe the product as a test build", () => {
  assert.doesNotMatch(publicPages, /产品仍处于测试阶段|测试阶段的模型|still in testing|during testing|当前版本尚未接入客服提交渠道/);
  assert.match(publicPages, /在账号设置下载账户数据/);
  assert.match(publicPages, /support@righttoken\.ai/);
  assert.doesNotMatch(core, /这台本地服务器|this local server/);
});

test("public and sign-in copy does not promise unmeasured AI-detector outcomes", () => {
  for (const page of [publicPages, auth]) {
    assert.doesNotMatch(page, /降低常见检测工具显示的 AI 生成率|降低 AI 生成率|Lower AI scores|lower the AI-generation rate reported by common detectors|提高通过 AI 生成检测的可能性/);
  }
  assert.match(auth, /平台不测量或保证第三方 AI 检测分数/);
});
