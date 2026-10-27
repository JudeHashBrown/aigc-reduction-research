import assert from "node:assert/strict";
import test from "node:test";
import { billableChars } from "../src/billing-text.js";
import { canStartModification, deterministicCleanupCount, snapshotMatchesDraft, workbenchAction } from "../src/workbench-action.js";

const finding = (pattern_id, paragraph, handling = "review", language = "en") => ({
  pattern_id, paragraph, handling, language,
});

test("every completed diagnosis can start modification, including clear and review-only reports", () => {
  const reports = [
    { summary: { findings: 0, auto_rewrite_candidates: 0, status: "clear" }, findings: [] },
    { summary: { findings: 1, review_items: 1, auto_rewrite_candidates: 0 }, findings: [finding("EN-S01", 1)] },
    { summary: { findings: 1, auto_rewrite_candidates: 0 }, findings: [finding("EN-S11", 1)] },
    { summary: { findings: 1, auto_rewrite_candidates: 0 }, findings: [finding("EN-F01", 1, "safe")] },
    { summary: { findings: 1, auto_rewrite_candidates: 0 }, findings: [finding("B6", 1, "review", "zh")] },
    { summary: { findings: 1 }, findings: [finding("C12", 1, "rewrite", "zh")] },
    { text: "It was found that the estimate is stable. 这是说明。", summary: { findings: 1, auto_rewrite_candidates: 0 }, findings: [finding("EN-S11", 1)] },
  ];
  for (const report of reports) assert.equal(workbenchAction(report), "rewrite");
  assert.equal(workbenchAction(null), "analyze");
});

test("the main modify button is enabled after each diagnosis outcome when account limits permit", () => {
  const settings = { llmConfigured: true, allowedStrengths: ["conservative"], mode: "conservative", withinJobLimit: true, hasEnoughBalance: true };
  for (const [status, findings] of [
    ["clear", []],
    ["review", [finding("EN-S01", 1)]],
    ["review", [finding("EN-F01", 1, "safe")]],
    ["needs_work", [finding("C12", 1, "rewrite", "zh")]],
  ]) {
    const report = { summary: { status, findings: findings.length, auto_rewrite_candidates: 0 }, findings };
    assert.equal(canStartModification({ report, ...settings }), true, status);
  }
  assert.equal(canStartModification({ report: null, ...settings }), false);
  assert.equal(canStartModification({ report: { summary: { status: "clear" } }, ...settings, hasEnoughBalance: false }), false);
  assert.equal(canStartModification({ report: { summary: { status: "clear" } }, ...settings, llmConfigured: false }), false);
});

test("English format-only findings do not expose a cleanup that cannot run", () => {
  assert.equal(deterministicCleanupCount({ summary: { safe_fixes: 1 }, findings: [finding("EN-F01", 1, "safe")] }), 0);
  assert.equal(deterministicCleanupCount({ findings: [finding("EN-F02", 1, "safe")] }), 0);
  assert.equal(deterministicCleanupCount({ findings: [finding("D19", 1, "safe", "zh")] }), 1);
});

test("an over-limit English paste can be trimmed to the 800-character boundary", () => {
  const pasted = `${"a".repeat(800)} extra`;
  assert.equal(billableChars(pasted), 805);
  assert.equal(billableChars(pasted.slice(0, 800)), 800);
  assert.equal(billableChars("one two three."), 12);
});

test("editing during a rewrite cannot overwrite the newer current draft", () => {
  assert.equal(snapshotMatchesDraft("original", 0, "original", 0), true);
  assert.equal(snapshotMatchesDraft("original", 0, "edited", 1), false);
  assert.equal(snapshotMatchesDraft("original", 0, "original", 2), false);
});
