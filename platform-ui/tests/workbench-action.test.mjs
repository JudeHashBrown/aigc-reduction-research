import assert from "node:assert/strict";
import test from "node:test";
import { billableBreakdown, billableChars, billableUnitLabel } from "../src/billing-text.js";
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

test("an over-limit English paste can be trimmed to the 800-word boundary", () => {
  const withinLimit = "word ".repeat(800);
  const pasted = `${withinLimit}extra`;
  assert.equal(billableChars(pasted), 801);
  assert.equal(billableChars(withinLimit), 800);
  assert.equal(billableChars("one two three."), 3);
  assert.equal(billableUnitLabel(withinLimit, true), "words");
});

test("mixed billing matches the server's English-word and Han-character rules", () => {
  for (const [value, expected] of [
    ["中 文\nA\t😀", 4],
    ["one two, 3", 3],
    ["state-of-the-art", 4],
    ["don't stop", 2],
    ["don’t stop", 2],
    ["3.14", 2],
    ["汉字AI research", 4],
    ["カナ 한글", 4],
    ["café cafe\u0301", 2],
    ["A\u200bB", 1],
    ["A\u0085B", 2],
    ["A\ufeffB", 1],
    ["éé", 1],
    ["ªª", 1],
    ["ºº", 1],
    ["ᵃᵃ", 1],
    ["ＡＡ", 1],
    ["\u{A7CB}\u{A7CB}", 1],
    ["\u{10D40}\u{10D41}", 1],
    ["a\u0897b", 1],
    ["a\u{1B4E}b", 2],
    ["\u{16FE2}\u{16FE2}", 0],
    ["😀🧪", 2],
    ["!? .,", 0],
  ]) assert.equal(billableChars(value), expected, JSON.stringify(value));
  assert.deepEqual(billableBreakdown("汉字AI research"), { total: 4, words: 2, han: 2, other: 0 });
  assert.equal(billableUnitLabel("中文", true), "Chinese characters");
  assert.equal(billableUnitLabel("中文AI", true), "text units");
});

test("editing during a rewrite cannot overwrite the newer current draft", () => {
  assert.equal(snapshotMatchesDraft("original", 0, "original", 0), true);
  assert.equal(snapshotMatchesDraft("original", 0, "edited", 1), false);
  assert.equal(snapshotMatchesDraft("original", 0, "original", 2), false);
});
