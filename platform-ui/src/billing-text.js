// Keep the browser's quota preview aligned with engine/normalize.py and
// web/billing.py. In particular, do not NFC-compose combining characters:
// the server deliberately preserves them and bills by Unicode code point.
const INVISIBLE = /[\u00AD\u180E\u200B-\u200D\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/gu;
const VARIATION = /[\uFE00-\uFE0F]/gu;
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/gu;

export function billableChars(text) {
  const cleaned = String(text || "")
    .replace(INVISIBLE, "")
    .replace(VARIATION, "")
    .replace(CONTROL, "");
  let count = 0;
  for (const char of cleaned) {
    if (!/^\s$/u.test(char)) count += 1;
  }
  return count;
}
