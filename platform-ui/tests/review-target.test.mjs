import assert from "node:assert/strict";
import test from "node:test";
import { reviewTargetFromFinding } from "../src/review-target.js";

test("located findings of any handling can request guarded modification", () => {
  const finding = { pattern_id: "EN-S01", handling: "review", start: 10, end: 31, matched: "alpha, beta, and gamma" };
  assert.deepEqual(reviewTargetFromFinding(finding), {
    pattern_id: "EN-S01", start: 10, end: 31, matched: "alpha, beta, and gamma",
  });
  assert.deepEqual(reviewTargetFromFinding({ ...finding, pattern_id: "EN-V-T1", handling: "rewrite" }), {
    pattern_id: "EN-V-T1", start: 10, end: 31, matched: "alpha, beta, and gamma",
  });
  assert.deepEqual(reviewTargetFromFinding({ ...finding, pattern_id: "B6", handling: "safe", end: 600 }), {
    pattern_id: "B6", start: 10, end: 600, matched: "alpha, beta, and gamma",
  });
  assert.equal(reviewTargetFromFinding({ ...finding, start: -1 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, end: 10 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, end: 3511 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, matched: "" }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, start: 10.5 }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, start: true }), null);
  assert.equal(reviewTargetFromFinding({ ...finding, pattern_id: "" }), null);
  assert.equal(reviewTargetFromFinding(null), null);
});
