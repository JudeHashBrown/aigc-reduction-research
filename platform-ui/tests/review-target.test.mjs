import assert from "node:assert/strict";
import test from "node:test";
import { reviewTargetFromFinding } from "../src/review-target.js";

test("only a located EN-S01 finding can request guarded automatic adjustment", () => {
  const finding = { pattern_id: "EN-S01", handling: "review", start: 10, end: 31, matched: "alpha, beta, and gamma" };
  assert.deepEqual(reviewTargetFromFinding(finding), {
    pattern_id: "EN-S01", start: 10, end: 31, matched: "alpha, beta, and gamma",
  });
  assert.equal(reviewTargetFromFinding({ ...finding, pattern_id: "EN-V-T1" }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, handling: "rewrite" }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, start: -1 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, end: 10 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, end: 600 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, matched: "" }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, start: 10.5 }), null);
  assert.equal(reviewTargetFromFinding(null), null);
});
