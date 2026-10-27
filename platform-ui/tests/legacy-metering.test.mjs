import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import { billableChars } from '../src/billing-text.js';

test('legacy workbench preview uses the same mixed-language meter', () => {
  const source = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');
  const start = source.indexOf('function localBillableChars(text) {');
  const end = source.indexOf('\nfunction updateComposer()', start);
  assert.ok(start >= 0 && end > start);
  const legacyCount = runInNewContext(`${source.slice(start, end)}\nlocalBillableChars`);
  for (const sample of [
    'one two three.', 'one-two don\'t', '中文 English 2026',
    'e\u0301 é', 'A\u200bB', 'ªª ºº ᵃᵃ', '日本語 한글 😀',
    '... ---', '\u00a0\u2000\u2028', '\u{16FE2}',
  ]) {
    assert.equal(legacyCount(sample), billableChars(sample), JSON.stringify(sample));
  }
});
