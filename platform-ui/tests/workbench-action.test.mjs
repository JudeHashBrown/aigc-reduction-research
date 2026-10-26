import assert from "node:assert/strict";
import test from "node:test";
import { billableChars } from "../src/billing-text.js";
import { deterministicCleanupCount, snapshotMatchesDraft, workbenchAction } from "../src/workbench-action.js";

const finding = (pattern_id, paragraph, handling = "review", language = "en") => ({
  pattern_id, paragraph, handling, language,
});

test("an English rule-of-three review opens manual editing, not an empty rewrite job", () => {
  const report = { summary: { findings: 1, review_items: 1, rewrite_items: 0, auto_rewrite_candidates: 0 }, findings: [finding("EN-S01", 1)] };
  assert.equal(workbenchAction(report), "edit");
  assert.equal(workbenchAction({ ...report, summary: { ...report.summary, rewrite_items: 1 } }), "edit");
  assert.equal(workbenchAction({ ...report, findings: [finding("EN-S01", 1), finding("EN-V-T1", 1)] }), "edit");
});

test("the service candidate count decides whether English findings can start a rewrite", () => {
  const report = { summary: { findings: 2, rewrite_items: 0, auto_rewrite_candidates: 1 }, findings: [finding("EN-S01", 1), finding("EN-V-T1", 2)] };
  assert.equal(workbenchAction(report), "rewrite");
  assert.equal(workbenchAction({ ...report, summary: { ...report.summary, auto_rewrite_candidates: 0 }, findings: [finding("EN-S11", 1)] }), "edit");
  assert.equal(workbenchAction({ ...report, summary: { ...report.summary, auto_rewrite_candidates: 0 }, findings: [finding("EN-F01", 1, "safe")] }), "edit");
  assert.equal(workbenchAction({ ...report, text: "It was found that the estimate is stable. 这是说明。", summary: { ...report.summary, auto_rewrite_candidates: 0 }, findings: [finding("EN-S11", 1)] }), "edit");
  assert.equal(workbenchAction({ ...report, summary: { findings: 1 }, findings: [finding("EN-V-T1", 1)] }), "edit");
});

test("Chinese review-only findings remain editable; rewrite findings can start a job", () => {
  const report = { summary: { findings: 1 }, findings: [finding("B6", 1, "review", "zh")] };
  assert.equal(workbenchAction(report), "edit");
  assert.equal(workbenchAction({ ...report, findings: [finding("C12", 1, "rewrite", "zh")] }), "rewrite");
  assert.equal(workbenchAction(null), "analyze");
  assert.equal(workbenchAction({ summary: { findings: 0 }, findings: [] }), "none");
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
