import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const workbench = readFileSync(fileURLToPath(new URL("../src/pages/LiveCorePages.jsx", import.meta.url)), "utf8");
const styles = readFileSync(fileURLToPath(new URL("../src/pages/live-core-pages.css", import.meta.url)), "utf8");

test("over-limit edit action appears to the left of its explanation", () => {
  const note = workbench.match(/\{!withinJobLimit && <div className="rt-live-limit-note rt-live-limit-note--edit">([\s\S]*?)<\/div>\}/)?.[1];
  assert.ok(note, "the over-limit note should render when the draft exceeds its limit");
  const buttonIndex = note.indexOf("<button");
  const explanationIndex = note.indexOf("<span>");
  assert.ok(buttonIndex >= 0 && explanationIndex >= 0 && buttonIndex < explanationIndex,
    "the edit button should precede the explanatory text");
  assert.match(note, /<button type="button" onClick=\{focusCurrentEditor\} aria-controls="rt-current-editor">/);
  assert.match(note, /Edit current draft" : "编辑当前稿/);
});

test("over-limit edit action focuses and reveals the current manuscript editor", () => {
  assert.match(workbench, /<textarea id="rt-current-editor" ref=\{currentEditorRef\}/);
  assert.match(workbench, /const focusCurrentEditor = \(\) => \{\s*const editor = currentEditorRef\.current;\s*if \(!editor\) return;\s*editor\.focus\(\{ preventScroll: true \}\);\s*editor\.scrollIntoView\(\{ block: "center", inline: "nearest" \}\);\s*\};/);
});

test("left edit action and focused editor remain visible at desktop and mobile widths", () => {
  assert.match(styles, /\.rt-live-limit-note \{[^}]*display: flex;[^}]*\}/s);
  assert.match(styles, /\.rt-live-limit-note--edit button \{[^}]*min-height: 32px;[^}]*border: 2px solid var\(--rt-ink\);[^}]*\}/s);
  assert.match(styles, /\.rt-live-editor-panel\.is-current textarea:focus \{[^}]*box-shadow: inset 0 0 0 3px #[0-9a-f]+;[^}]*\}/s);
  assert.match(styles, /@media \(max-width: 760px\) \{[\s\S]*?\.rt-live-limit-note \{ flex-wrap: wrap; \}/);
});
