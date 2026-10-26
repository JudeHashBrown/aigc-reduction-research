import assert from "node:assert/strict";
import test from "node:test";
import { changedPassages, diffChange } from "../src/change-highlights.js";

function reconstructed(parts) {
  return parts.map((part) => part.text).join("");
}

test("English word edits highlight only the changed word and preserve spacing", () => {
  const before = "The very robust model.\nNext line.";
  const after = "The robust model.\nNext line.";
  const result = diffChange(before, after);
  assert.equal(reconstructed(result.before), before);
  assert.equal(reconstructed(result.after), after);
  assert.ok(result.before.some((part) => part.kind === "removed" && part.text.includes("very")));
  assert.ok(result.before.some((part) => part.kind === "same" && part.text.includes("robust model.")));
  assert.equal(result.after.some((part) => part.kind === "added"), false);
  assert.equal(result.fallback, false);
});

test("Chinese, punctuation, emoji, and whitespace stay byte-for-byte intact", () => {
  const before = "研究方法：甲、乙。\n😀";
  const after = "研究方法：甲、丙！\n😀";
  const result = diffChange(before, after);
  assert.equal(reconstructed(result.before), before);
  assert.equal(reconstructed(result.after), after);
  assert.ok(result.before.some((part) => part.kind === "removed" && part.text.includes("乙")));
  assert.ok(result.after.some((part) => part.kind === "added" && part.text.includes("丙")));
  assert.equal(result.fallback, false);
});

test("pure insertions, deletions, unchanged text, and empty strings have exact sides", () => {
  for (const [before, after] of [["A B", "A new B"], ["A new B", "A B"], ["same", "same"], ["", ""], ["", "新增"], ["deleted", ""]]) {
    const result = diffChange(before, after);
    assert.equal(reconstructed(result.before), before);
    assert.equal(reconstructed(result.after), after);
  }
});

test("large unrelated passages use bounded fallback, while long common context remains precise", () => {
  const large = diffChange("甲".repeat(900), "乙".repeat(900));
  assert.equal(large.fallback, true);
  assert.equal(reconstructed(large.before), "甲".repeat(900));
  assert.equal(reconstructed(large.after), "乙".repeat(900));
  const common = "原文".repeat(5_000);
  const small = diffChange(`${common}旧${common}`, `${common}新${common}`);
  assert.equal(small.fallback, false);
  assert.deepEqual(small.before.filter((part) => part.kind === "removed").map((part) => part.text), ["旧"]);
  assert.deepEqual(small.after.filter((part) => part.kind === "added").map((part) => part.text), ["新"]);
});

test("literal markup stays text for React to escape when rendered", () => {
  const before = "<script>alert(1)</script>";
  const after = "<script>alert(2)</script>";
  const result = diffChange(before, after);
  assert.equal(reconstructed(result.before), before);
  assert.equal(reconstructed(result.after), after);
  assert.ok(result.before.some((part) => part.kind === "removed"));
});

test("cleanup review shows every changed line and falls back when structure changes", () => {
  assert.deepEqual(changedPassages("First\nOld word\nLast", "First\nNew word\nLast"), [
    { original: "Old word", rewritten: "New word" },
  ]);
  assert.deepEqual(changedPassages("First\nLast", "First\nInserted\nLast"), [
    { original: "First\nLast", rewritten: "First\nInserted\nLast" },
  ]);
  assert.deepEqual(changedPassages("same", "same"), []);
});
