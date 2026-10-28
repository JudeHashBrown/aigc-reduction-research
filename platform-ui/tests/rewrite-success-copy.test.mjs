import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const workbench = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");
const successMessages = workbench.match(/\} else if \(checkPassed\) \{([\s\S]*?)\n        \}\n        break;/)?.[1];

test("rewrite success reports a saved draft and accepted candidates without model call counts", () => {
  assert.ok(successMessages, "the completed rewrite should set a success message");
  assert.match(successMessages, /修改稿已保存/);
  assert.match(successMessages, /Revised draft saved/);
  assert.match(successMessages, /采纳 \$\{accepted\} \/ \$\{targeted\} 处段落候选/);
  assert.match(successMessages, /\$\{accepted\} of \$\{targeted\} paragraph candidates accepted/);
  assert.doesNotMatch(successMessages, /模型调用|model requests|\$\{calls\}/i);
});
