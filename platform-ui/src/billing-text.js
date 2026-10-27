// Keep this preview aligned with web/billing.py. The historical function name
// remains because existing screens and saved-document code already use it.
const INVISIBLE = /\p{Cf}/u;
const VARIATION = /[\uFE00-\uFE0F\u{E0100}-\u{E01EF}]/u;
const CONTROL = /\p{Cc}/u;
const LATIN = /\p{Script=Latin}/u;
const LETTER = /\p{Letter}/u;
const DIGIT = /\p{Decimal_Number}/u;
const HAN = /\p{Script=Han}/u;
const MARK = /\p{Mark}/u;
const PUNCTUATION = /\p{Punctuation}/u;
// Python str.isspace() includes U+0085 and U+001C–U+001F but excludes BOM.
// Preserve whitespace as a word separator before dropping control characters.
const WHITESPACE = /^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]$/u;

export function billableBreakdown(text) {
  const characters = Array.from(String(text || ""))
    .filter((char) => WHITESPACE.test(char) || !(INVISIBLE.test(char) || VARIATION.test(char) || CONTROL.test(char)));
  let words = 0;
  let han = 0;
  let other = 0;
  let inWord = false;

  for (let index = 0; index < characters.length; index += 1) {
    const char = characters[index];
    const latinLetter = LATIN.test(char) && LETTER.test(char);
    if (latinLetter || DIGIT.test(char)) {
      if (!inWord) words += 1;
      inWord = true;
      continue;
    }
    if (MARK.test(char) && inWord) continue;
    if ((char === "'" || char === "’") && inWord
      && ((LATIN.test(characters[index + 1] || "") && LETTER.test(characters[index + 1] || "")) || DIGIT.test(characters[index + 1] || ""))) {
      continue;
    }

    inWord = false;
    if (HAN.test(char) && !PUNCTUATION.test(char)) han += 1;
    else if (!WHITESPACE.test(char) && !PUNCTUATION.test(char)) other += 1;
  }
  return { total: words + han + other, words, han, other };
}

export function billableChars(text) {
  return billableBreakdown(text).total;
}

export function billableUnitLabel(text, isEnglish) {
  const { words, han, other } = billableBreakdown(text);
  if (words && !han && !other) return isEnglish ? "words" : "英文词";
  if (han && !words && !other) return isEnglish ? "Chinese characters" : "汉字";
  return isEnglish ? "text units" : "正文单位";
}
