// A bounded, text-only comparison for a single passage. Keep every character
// (including whitespace) so either side can be copied back to its exact input.
const TOKEN_PATTERN = /\p{Script=Han}|[\p{L}\p{M}\p{N}]+(?:['’][\p{L}\p{M}\p{N}]+)*|\s+|[^\s]/gu;
const MAX_MATRIX_CELLS = 40_000;
const MAX_MIDDLE_TOKENS = 700;

function tokens(text) {
  return String(text ?? "").match(TOKEN_PATTERN) || [];
}

function append(operations, kind, value) {
  if (!value) return;
  const previous = operations[operations.length - 1];
  if (previous?.kind === kind) previous.text += value;
  else operations.push({ kind, text: value });
}

function sides(operations, fallback) {
  return {
    before: operations.filter((item) => item.kind !== "added")
      .map((item) => ({ kind: item.kind, text: item.text })),
    after: operations.filter((item) => item.kind !== "removed")
      .map((item) => ({ kind: item.kind, text: item.text })),
    fallback,
  };
}

/**
 * Compare real before/after text. English is grouped by words, Han text by
 * character, and punctuation/whitespace is preserved exactly. For a very
 * large changed middle, highlight that middle as a block instead of running
 * a quadratic alignment that could freeze the workbench.
 */
export function diffChange(beforeText, afterText) {
  const before = String(beforeText ?? "");
  const after = String(afterText ?? "");
  if (before === after) return sides(before ? [{ kind: "same", text: before }] : [], false);

  const left = tokens(before);
  const right = tokens(after);
  let prefix = 0;
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) prefix += 1;
  let suffix = 0;
  while (suffix < left.length - prefix && suffix < right.length - prefix
    && left[left.length - suffix - 1] === right[right.length - suffix - 1]) suffix += 1;

  const removed = left.slice(prefix, left.length - suffix);
  const added = right.slice(prefix, right.length - suffix);
  const operations = [];
  append(operations, "same", left.slice(0, prefix).join(""));

  const fallback = removed.length * added.length > MAX_MATRIX_CELLS
    || removed.length + added.length > MAX_MIDDLE_TOKENS;
  if (fallback || !removed.length || !added.length) {
    append(operations, "removed", removed.join(""));
    append(operations, "added", added.join(""));
  } else {
    const width = added.length + 1;
    const table = new Uint16Array((removed.length + 1) * width);
    for (let i = removed.length - 1; i >= 0; i -= 1) {
      for (let j = added.length - 1; j >= 0; j -= 1) {
        table[i * width + j] = removed[i] === added[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < removed.length || j < added.length) {
      if (i < removed.length && j < added.length && removed[i] === added[j]) {
        append(operations, "same", removed[i]); i += 1; j += 1;
      } else if (i < removed.length && (j === added.length
        || table[(i + 1) * width + j] >= table[i * width + j + 1])) {
        append(operations, "removed", removed[i]); i += 1;
      } else {
        append(operations, "added", added[j]); j += 1;
      }
    }
  }

  append(operations, "same", suffix ? left.slice(left.length - suffix).join("") : "");
  return sides(operations, fallback);
}

/** List changed lines without hiding any edits; fall back to one full-text row
 * if line alignment changes or a very large cleanup affects many lines. */
export function changedPassages(beforeText, afterText) {
  const before = String(beforeText ?? "");
  const after = String(afterText ?? "");
  if (before === after) return [];
  const oldLines = before.split("\n");
  const newLines = after.split("\n");
  if (oldLines.length !== newLines.length) return [{ original: before, rewritten: after }];
  const rows = [];
  for (let index = 0; index < oldLines.length; index += 1) {
    if (oldLines[index] !== newLines[index]) {
      rows.push({ original: oldLines[index], rewritten: newLines[index] });
      if (rows.length > 200) return [{ original: before, rewritten: after }];
    }
  }
  return rows;
}
