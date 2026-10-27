"""Bilingual facade for the product editing API.

The newer product UI was originally wired only to :mod:`humanizer_cn`, while
the repository's earlier diagnostic/rewrite stack already had paragraph-level
English support.  This module keeps the stable v1 response shape and routes
each language to the engine that has actually been written and tested for it.

It deliberately reports editing signals rather than an "AI percentage".
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import guard
import humanizer_cn
from codefix import codefix
from diagnose import detect_lang, diagnose, split_paragraphs
from llm import Client, LLMError
import rewrite as bilingual_rewrite


ENGLISH_CHECKS = 13  # 12 sentence/paragraph rules + the vocabulary family.
ENGLISH_CATEGORIES = {
    "EN-V": "英文用词",
    "EN-S": "英文句式与结构",
    "EN-F": "排版与格式",
}

_EN_CONSTRAINTS = re.compile(
    r"\b(?:not|no|never|neither|nor|without|cannot|can't|won't|didn't|doesn't|"
    r"may|might|could|possibly|perhaps|likely|unlikely|appears?|seems?|"
    r"plan(?:ned|s)?|intend(?:ed|s)?|expect(?:ed|s)?|propos(?:e|ed|es)|"
    r"will|would|future|ongoing|currently|already|completed?|released?|"
    r"if|unless|only if|provided that|at least|at most|no more than|"
    r"some|most|all|none|partly|partially)\b",
    re.I,
)

_CJK = re.compile(r"[\u3400-\u9fff]")
_ENGLISH_PHRASE = re.compile(
    r"\b[A-Za-z][A-Za-z'-]*\b(?:[ \t]+\b[A-Za-z][A-Za-z'-]*\b){2,}"
)


def _is_latin_letter(char: str) -> bool:
    return (unicodedata.category(char).startswith("L")
            and "LATIN" in unicodedata.name(char, ""))


def _latin_islands(text: str) -> List[str]:
    """Return exact Latin/ASCII islands separated by CJK text.

    Keeping the whole island (rather than words alone) also protects syntax in
    ``foo::bar``, ``input/output``, ``scikit.learn`` and quoted/code literals.
    """
    islands: List[str] = []
    current: List[str] = []
    has_latin = False

    def flush() -> None:
        nonlocal current, has_latin
        if current and has_latin:
            islands.append("".join(current))
        current, has_latin = [], False

    for char in text:
        if _is_latin_letter(char):
            current.append(char)
            has_latin = True
        elif char.isascii():
            # ASCII digits, spaces and punctuation are part of an identifier,
            # code literal or English phrase until CJK text/punctuation ends
            # the island.  Whitespace-only islands are discarded by flush().
            current.append(char)
        else:
            flush()
    flush()
    return islands


def _paragraph_language(text: str) -> str:
    """Classify inline bilingual prose without mistaking model-name lists."""
    has_cjk = bool(_CJK.search(text))
    has_latin = bool(_latin_islands(text))
    if has_cjk and has_latin and _ENGLISH_PHRASE.search(text):
        return "mixed"
    if has_cjk:
        return "zh"
    return "en" if has_latin else detect_lang(text)


def _has_cjk_latin(text: str) -> bool:
    return bool(_CJK.search(text) and _latin_islands(text))


def _editing_language(text: str) -> str:
    """Route CJK+Latin paragraphs to a non-LLM protected lane."""
    language = _paragraph_language(text)
    return "protected" if language == "zh" and _has_cjk_latin(text) else language


def _languages(text: str) -> List[str]:
    return [_paragraph_language(paragraph.text) for paragraph in split_paragraphs(text)]


def _span_language(text: str, start: int, end: int) -> Optional[str]:
    snippet = text[start:end]
    if _CJK.search(snippet):
        return "mixed" if _ENGLISH_PHRASE.search(snippet) else "zh"
    if _latin_islands(snippet):
        return "en"
    paragraphs = split_paragraphs(text)
    for paragraph in paragraphs:
        if paragraph.start <= start and end <= paragraph.end:
            return _paragraph_language(paragraph.text)
    return None


def _english_view(text: str) -> str:
    """Mask CJK characters while preserving offsets for English diagnosis."""
    cjk_punctuation = "。！？；，、：‘’“”（）《》【】"
    return "".join(
        " " if _CJK.match(char) or char in cjk_punctuation else char
        for char in text
    )


def _paragraph_number(text: str, position: int) -> int:
    for index, paragraph in enumerate(split_paragraphs(text), start=1):
        if paragraph.start <= position <= paragraph.end:
            return index
    return 0


def _english_category(rule_id: str) -> Tuple[str, str]:
    if rule_id.startswith("V-"):
        key = "EN-V"
    elif rule_id.startswith("F"):
        key = "EN-F"
    else:
        key = "EN-S"
    return key, ENGLISH_CATEGORIES[key]


def _handling(value: str) -> str:
    return {"code": "safe", "llm": "rewrite", "report": "review"}.get(
        value, "review")


def _map_english_finding(item: Dict, text: str) -> Dict:
    category, category_name = _english_category(str(item.get("rule_id", "")))
    rule_id = str(item.get("rule_id", ""))
    return {
        "pattern_id": f"EN-{rule_id}",
        "category": category,
        "category_name": category_name,
        "name": item.get("name") or rule_id,
        "severity": item.get("severity") or "medium",
        "start": int(item.get("start") or 0),
        "end": int(item.get("end") or 0),
        "matched": text[int(item.get("start") or 0):int(item.get("end") or 0)],
        # A CJK-masked paragraph can become whitespace-only and disappear from
        # diagnose()'s paragraph list.  Recompute against the original text so
        # mixed documents retain the correct one-based paragraph number.
        "paragraph": _paragraph_number(text, int(item.get("start") or 0)),
        "reason": item.get("explain") or "该英文表达需要结合上下文核验。",
        "suggestion": item.get("fix") or "Review this expression in context.",
        "handling": _handling(str(item.get("handling") or "")),
        "replacement": None,
        "language": "en",
    }


def _dedupe_findings(items: Iterable[Dict]) -> List[Dict]:
    seen = set()
    result = []
    for item in sorted(items, key=lambda value: (
            int(value.get("start") or 0), int(value.get("end") or 0),
            str(value.get("pattern_id") or ""))):
        key = (item.get("pattern_id"), item.get("start"), item.get("end"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def anchors(text: str) -> Dict:
    result = humanizer_cn.anchors(text)
    english = [match.group(0) for match in _EN_CONSTRAINTS.finditer(text)]
    constraints = list(result.get("constraints") or [])
    for value in english:
        if value not in constraints:
            constraints.append(value)
    result["constraints"] = constraints
    result.setdefault("counts", {})["constraints"] = len(constraints)
    return result


def analyze(text: str) -> Dict:
    """Return one stable report for Chinese, English, or mixed documents."""
    text = text or ""
    languages = _languages(text)
    has_zh = any(language in {"zh", "mixed"} for language in languages)
    has_en = any(language in {"en", "mixed"} for language in languages)
    if not has_en:
        report = humanizer_cn.analyze(text)
        report["language"] = "zh"
        report["language_counts"] = {"zh": languages.count("zh"), "en": 0}
        return report

    # A paragraph can contain a complete English sentence plus Chinese notes.
    # Diagnose a same-length CJK-masked view so English rules retain exact
    # source offsets instead of routing the entire paragraph through Chinese.
    legacy = diagnose(_english_view(text))
    english_findings = []
    for item in legacy.get("findings", []):
        # Global format findings are useful for either language.  Paragraph
        # findings must come from an English paragraph to avoid duplicating the
        # Chinese engine's more conservative product policy.
        span_language = _span_language(
            text, int(item.get("start") or 0), int(item.get("end") or 0))
        # Absolute spans survive the same-length mask; para_index does not when
        # an all-Chinese paragraph becomes whitespace and is omitted.
        if span_language == "en":
            english_findings.append(_map_english_finding(item, text))

    chinese_findings: List[Dict] = []
    if has_zh:
        chinese = humanizer_cn.analyze(text)
        for item in chinese.get("findings", []):
            if _span_language(text, int(item.get("start") or 0),
                              int(item.get("end") or 0)) == "zh":
                mapped = dict(item)
                mapped["language"] = "zh"
                chinese_findings.append(mapped)

    findings = _dedupe_findings([*chinese_findings, *english_findings])
    severity = {
        level: sum(1 for item in findings if item.get("severity") == level)
        for level in ("high", "medium", "low")
    }
    handling = {
        mode: sum(1 for item in findings if item.get("handling") == mode)
        for mode in ("safe", "rewrite", "review")
    }
    auto_rewrite_candidates = _auto_rewrite_candidate_count(text, findings)
    affected = {int(item.get("paragraph") or 0) for item in findings}
    if severity["high"] >= 2 or severity["high"] + severity["medium"] >= 6:
        status, label = "needs_work", "需要重点优化"
    elif findings:
        status, label = "review", "有可优化表达"
    else:
        status, label = "clear", "未发现明显模板化表达"

    checks = (31 if has_zh else 0) + (ENGLISH_CHECKS if has_en else 0)
    language = "mixed" if has_zh and has_en else "en"
    zh_count = sum(language in {"zh", "mixed"} for language in languages)
    en_count = sum(language in {"en", "mixed"} for language in languages)
    return {
        "text": text,
        "summary": {
            "n_chars": len(re.sub(r"\s", "", text)),
            "n_paragraphs": len(languages),
            "checks": checks,
            "findings": len(findings),
            "high": severity["high"],
            "medium": severity["medium"],
            "low": severity["low"],
            "safe_fixes": handling["safe"],
            "rewrite_items": handling["rewrite"],
            "review_items": handling["review"],
            "auto_rewrite_candidates": auto_rewrite_candidates,
            "affected_paragraphs": len(affected),
            "status": status,
            "status_label": label,
            "language": language,
        },
        "findings": findings,
        "anchors": anchors(text),
        "categories": {**humanizer_cn.CATEGORY_NAMES, **ENGLISH_CATEGORIES},
        "language": language,
        "language_counts": {"zh": zh_count, "en": en_count},
        "disclaimer": (
            "这些是可核对的中英文表达问题，不是 AI 率，也不证明文本由谁撰写。"
            "检测器效果需按平台、版本和文体另行校准。"
        ),
    }


def _merge_guard_results(results: Sequence[Dict]) -> Dict:
    if len(results) == 1:
        return results[0]
    added: Dict[str, List[str]] = {}
    removed: Dict[str, List[str]] = {}
    semantic_changed = False
    semantic_changes: Dict = {}
    terms = set()
    for result in results:
        for target, source in ((added, result.get("added", {})),
                               (removed, result.get("removed", {}))):
            for key, values in source.items():
                target.setdefault(key, [])
                target[key] = sorted(set(target[key]) | set(values))
        terms.update(result.get("terms_lost") or [])
        semantic_changed = semantic_changed or bool(result.get("semantic_changed"))
        semantic_changes.update((result.get("semantic") or {}).get("changed") or {})
    return {
        "added": added,
        "removed": removed,
        "n_added": sum(len(values) for values in added.values()),
        "n_removed": sum(len(values) for values in removed.values()),
        "terms_lost": sorted(terms),
        "fabricated": any(bool(result.get("fabricated")) for result in results),
        "semantic": {"changed": semantic_changes, "ok": not semantic_changed},
        "semantic_changed": semantic_changed,
    }


def _inline_mixed_latin_changes(src: str, out: str) -> List[Dict]:
    """Protect every Latin token inside a Chinese/English mixed paragraph.

    A Chinese semantic guard cannot know that a one-off English word such as
    ``deployment`` is load-bearing, while a generic English term list cannot
    reliably distinguish it from prose.  Exact ordered tokens are therefore
    the safety boundary for inline bilingual paragraphs.
    """
    before = split_paragraphs(src)
    after = split_paragraphs(out)
    changes: List[Dict] = []
    protected_indexes = []
    for index, paragraph in enumerate(before):
        # Chinese academic prose frequently embeds comma-separated model names
        # (bert、gpt、transformer) without forming a three-word English phrase.
        # Protect those tokens too, even when the paragraph is classified zh.
        if not _has_cjk_latin(paragraph.text):
            continue
        protected_indexes.append(index)
        expected = _latin_islands(paragraph.text)
        actual = (_latin_islands(after[index].text)
                  if index < len(after) else [])
        if expected != actual:
            changes.append({
                "paragraph": index + 1,
                "before": expected,
                "after": actual,
                "reason": "同段中英混排的英文正文发生变化",
            })
    if protected_indexes and len(before) != len(after):
        changes.append({
            "paragraph": 0,
            "before": len(before),
            "after": len(after),
            "reason": "含中英混排时段落数量发生变化",
        })
    return changes


def _document_guard(src: str, out: str) -> Dict:
    labels = set(_languages(src)) or {"zh"}
    languages = set()
    for label in labels:
        languages.update({"zh", "en"} if label == "mixed" else {label})
    result = _merge_guard_results(
        [guard.compare(src, out, lang) for lang in sorted(languages)]
    )
    inline_changes = _inline_mixed_latin_changes(src, out)
    if inline_changes:
        result.setdefault("semantic", {}).setdefault("changed", {})[
            "混排英文正文"
        ] = inline_changes
        result["semantic"]["ok"] = False
        result["semantic_changed"] = True
    return result


def autofix(text: str) -> Dict:
    languages = _languages(text)
    if "en" not in languages:
        return humanizer_cn.autofix(text)
    before = analyze(text)
    fixed, raw_log = codefix(text)
    comparison = _document_guard(text, fixed)
    rolled_back = any(item.get("rule_id") == "GUARD" for item in raw_log)
    unsafe = (rolled_back or comparison.get("fabricated")
              or comparison.get("n_removed")
              or comparison.get("semantic_changed"))
    if unsafe:
        fixed = text
    log = [{
        "pattern_id": f"{('EN-' if item.get('lang') == 'en' else '')}{item.get('rule_id', '')}",
        "name": item.get("name") or item.get("rule_id") or "安全清理",
        "accepted": not unsafe and bool(item.get("count", 0)),
        "count": int(item.get("count") or 0),
        "language": item.get("lang"),
        **({"reason": "整体事实守卫未通过，未应用"} if unsafe else {}),
    } for item in raw_log]
    return {
        "text": fixed,
        "changed": fixed != text,
        "log": log,
        "before": before,
        "after": analyze(fixed),
        "guard": comparison,
    }


# A reported three-part list is usually a legitimate academic enumeration.
# Only this small, unambiguous subset can be rearranged without asking a model
# to decide which research variable or factual item may be removed.  All three
# source adjectives remain byte-for-byte identical and in the same order.
_S01_QUALITY_WORDS = frozenset({
    "accessible", "accurate", "clear", "concise", "consistent", "effective",
    "efficient", "fast", "flexible", "interpretable", "practical", "precise",
    "readable", "reliable", "reproducible", "resilient", "robust", "safe",
    "scalable", "secure", "simple", "stable", "transparent", "usable",
})
_S01_SIMPLE_LIST = re.compile(
    r"(?P<first>[A-Za-z]+),[ \t]+(?P<second>[A-Za-z]+),[ \t]+and[ \t]+"
    r"(?P<third>[A-Za-z]+)$", re.I,
)


def find_review_target(text: str, target: Dict) -> Optional[Dict]:
    """Find an exact, current EN-S01 report item; offsets are Unicode codepoints."""
    if not isinstance(target, dict) or target.get("pattern_id") != "EN-S01":
        return None
    start, end, matched = target.get("start"), target.get("end"), target.get("matched")
    if (type(start) is not int or type(end) is not int or not isinstance(matched, str)
            or not 0 <= start < end <= len(text) or end - start > 500
            or text[start:end] != matched):
        return None
    return next((item for item in analyze(text)["findings"]
                 if item.get("pattern_id") == "EN-S01"
                 and item.get("handling") == "review"
                 and item.get("start") == start and item.get("end") == end
                 and item.get("matched") == matched), None)


def find_edit_target(text: str, target: Dict) -> Optional[Dict]:
    """Resolve a selected finding against the current manuscript, not saved UI data."""
    if not isinstance(target, dict):
        return None
    start, end, matched = target.get("start"), target.get("end"), target.get("matched")
    pattern_id = target.get("pattern_id")
    if (type(start) is not int or type(end) is not int
            or not isinstance(pattern_id, str) or not isinstance(matched, str)
            or not 0 <= start < end <= len(text) or end - start > 3500
            or text[start:end] != matched):
        return None
    return next((item for item in analyze(text)["findings"]
                 if item.get("pattern_id") == pattern_id
                 and item.get("start") == start and item.get("end") == end
                 and item.get("matched") == matched), None)


def edit_review_finding(text: str, target: Dict) -> Dict:
    """Opt-in, deterministic edit of one safely recognizable EN-S01 finding.

    A normal list of variables, datasets or results is not a stylistic error.
    If the selected item is not a simple predicate adjective list, return the
    original untouched with an explicit reason instead of inventing a fix.
    """
    finding = find_review_target(text, target)
    if finding is None:
        raise ValueError("诊断项与当前正文不一致，请重新分析后再试。")
    before = analyze(text)
    start, end = finding["start"], finding["end"]
    matched = text[start:end]
    reason_code = "context_requires_review"
    reason = "此处可能是正常的学术列举；无法安全自动调整，建议保留原文并人工核对。"
    reason_en = ("This may be a legitimate academic list. No safe automatic "
                 "edit was applied; please review it in context.")
    replacement = matched
    triplet = _S01_SIMPLE_LIST.search(matched)
    if triplet:
        words = [triplet.group(key) for key in ("first", "second", "third")]
        preceding = text[:start] + matched[:triplet.start()]
        # Only a simple "is A, B, and C." predicate admits this syntax change.
        # Multiword variables and lists inside longer clauses stay untouched.
        if (all(word.lower() in _S01_QUALITY_WORDS for word in words)
                and len({word.lower() for word in words}) == 3
                and re.search(r"\bis[ \t]+$", preceding, re.I)
                and text[end:end + 1] == "."):
            replacement = (matched[:triplet.start()] + words[0] + " and "
                           + words[1] + " while remaining " + words[2])
            reason_code = "adjective_syntax_reordered"
            reason = "已调整简单形容词并列句的句法，三项原词及顺序均保留；请人工核对语气与上下文。"
            reason_en = ("The simple adjective list was restructured while "
                         "preserving all three terms and their order. Please review the tone and context.")

    output = text[:start] + replacement + text[end:]
    comparison = _document_guard(text, output)
    unsafe = (comparison.get("fabricated") or comparison.get("n_removed")
              or comparison.get("terms_lost") or comparison.get("semantic_changed"))
    after = analyze(output)
    before_s01 = sum(item.get("pattern_id") == "EN-S01" for item in before["findings"])
    after_s01 = sum(item.get("pattern_id") == "EN-S01" for item in after["findings"])
    if replacement != matched and (unsafe or after_s01 >= before_s01
                                   or after["summary"]["findings"] >= before["summary"]["findings"]):
        output, replacement, after = text, matched, before
        comparison = _document_guard(text, text)
        reason_code = "guard_rejected"
        reason = "候选修改未通过事实或诊断复核，已保留原文；请人工核对。"
        reason_en = "The proposed edit failed verification, so the original was retained. Please review it manually."

    changed = output != text
    return {
        "text": output, "before": before, "after": after,
        "autofix": {"text": text, "changed": False, "log": []},
        "chunks": [{"index": int(finding.get("paragraph") or 1) - 1,
                    "lang": "en", "accepted": changed,
                    "reason": reason, "targets": ["EN-S01"],
                    "original": matched, "rewritten": replacement,
                    "candidates": []}],
        "n_chunks": 1, "n_accepted": int(changed), "n_safe_changes": int(changed),
        "changed": changed,
        "guard": {"fabricated": comparison.get("fabricated", False),
                  "added": comparison.get("added", {}),
                  "removed": comparison.get("removed", {}),
                  "detail": guard.describe(comparison),
                  "warnings": [], "status": "passed"},
        "review_target": {"pattern_id": "EN-S01", "start": start, "end": end,
                          "status": "changed" if changed else "unchanged",
                          "reason_code": reason_code, "reason": reason,
                          "reason_en": reason_en},
        "method": "Deterministic selected-finding edit + factual guard",
        "disclaimer": before["disclaimer"],
    }


_REQUESTED_SYSTEM = (
    "You are a careful academic copy editor. The author has explicitly asked "
    "for a visible wording edit. Make a small, useful change to expression or "
    "sentence structure, including when a detector found no issue. A finding "
    "is a clue, not proof that content is wrong. Preserve every claim, list "
    "item, number, citation, technical term, qualifier, negation, causal "
    "relation, and paragraph break. Do not add facts or invent sources. "
    "Keep Chinese and English passages in their original languages and copy "
    "embedded Latin identifiers exactly. If no faithful edit is possible, "
    "return the input unchanged. Output only the edited passage."
)


def _requested_prompt(source: str, findings: Sequence[Dict],
                      selected: Optional[Dict] = None) -> str:
    if selected is None:
        instructions = (
            "用户已点击修改。请对这段做至少一处可见且有意义的表达调整；"
            "无诊断线索也可以改善句法或精简冗余。真实列举须保留每一项。"
        )
        relevant = findings[:16]
    else:
        instructions = (
            "用户已点击这条线索的修改。只调整与选中线索有关的句法或用词；"
            "保留同一句中其他信息和完整列举。请输出整个待改片段。"
        )
        relevant = [selected]
    clues = [
        {"id": item.get("pattern_id"), "matched": item.get("matched"),
         "suggestion": item.get("suggestion")}
        for item in relevant
    ]
    return (instructions + "\n诊断线索：" + str(clues)
            + "\n待改片段：\n<<<TEXT>>>\n" + source + "\n<<<END>>>")


def _ordered_list_words_preserved(source: str, candidate: str) -> bool:
    """A style change must not silently remove a reported list component."""
    before = analyze(source)
    sentence_pattern = re.compile(r"[^\n.。！？!?；;]+[.。！？!?；;]?|[.。！？!?；;]")
    source_sentences = list(sentence_pattern.finditer(source))
    candidate_sentences = list(sentence_pattern.finditer(candidate))
    english_connectors = {"and", "or", "with", "as", "well", "together",
                          "along", "while", "remaining", "also"}
    for finding in before["findings"]:
        pattern_id = finding.get("pattern_id")
        if pattern_id not in {"EN-S01", "B6", "F29"}:
            continue
        index = next((position for position, sentence in enumerate(source_sentences)
                      if sentence.start() <= finding["start"]
                      and finding["end"] <= sentence.end()), None)
        if (index is None or len(source_sentences) != len(candidate_sentences)):
            return False
        source_sentence = source_sentences[index].group(0)
        candidate_sentence = candidate_sentences[index].group(0)
        if pattern_id == "EN-S01":
            # A verified S11 shell can be removed elsewhere in the same line
            # without changing any item of this three-part list.
            source_content_text = (
                bilingual_rewrite._strip_en_s11_shell(source_sentence)
                or source_sentence)
            source_content = Counter(word.lower() for word in re.findall(
                r"[A-Za-z][A-Za-z'-]*", source_content_text)
                if word.lower() not in english_connectors)
            candidate_content = Counter(word.lower() for word in re.findall(
                r"[A-Za-z][A-Za-z'-]*", candidate_sentence)
                if word.lower() not in english_connectors)
            if source_content != candidate_content:
                return False
            words = re.findall(r"[A-Za-z][A-Za-z'-]*",
                               candidate_sentence.lower())
            required = [word.lower() for word in re.findall(
                r"[A-Za-z][A-Za-z'-]*", finding["matched"])
                    if word.lower() not in {"and", "or"}]
            position = 0
            for word in required:
                try:
                    position = words.index(word, position) + 1
                except ValueError:
                    return False
        elif pattern_id in {"B6", "F29"}:
            source_content = Counter(char for char in source_sentence
                                     if _CJK.match(char) and char not in "和与以及")
            candidate_content = Counter(char for char in candidate_sentence
                                        if _CJK.match(char) and char not in "和与以及")
            if source_content != candidate_content:
                return False
            parts = [part.strip() for part in re.split(
                r"[、，,]|以及|和|与", finding["matched"]) if part.strip()]
            position = 0
            for part in parts:
                found = candidate_sentence.find(part, position)
                if found < 0:
                    return False
                position = found + len(part)
    return True


def _requested_candidate(source: str, raw: str) -> Dict:
    """Check a user-requested edit before any candidate reaches the manuscript."""
    candidate = humanizer_cn._restore_paragraph_separators(
        source, humanizer_cn._clean_model_output(raw))
    if not candidate or candidate.strip() == source.strip():
        return {"ok": False, "text": source, "reason": "候选没有实际修改"}
    ratio = len(candidate) / max(1, len(source))
    if not 0.55 <= ratio <= 1.45:
        return {"ok": False, "text": candidate, "reason": "候选长度偏离过大"}
    paragraph_error = humanizer_cn._paragraph_safety_error(source, candidate)
    if paragraph_error:
        return {"ok": False, "text": candidate,
                "reason": paragraph_error["reason"]}
    comparison = _document_guard(source, candidate)
    if (comparison.get("fabricated") or comparison.get("n_removed")
            or comparison.get("terms_lost") or comparison.get("semantic_changed")):
        return {"ok": False, "text": candidate,
                "reason": "事实守卫未通过：" + guard.describe(comparison)}
    warnings = humanizer_cn._anchor_warnings(source, candidate)
    if warnings:
        return {"ok": False, "text": candidate,
                "reason": "；".join(warnings)}
    if not _ordered_list_words_preserved(source, candidate):
        return {"ok": False, "text": candidate,
                "reason": "列举中的原项或顺序发生变化"}
    before, after = analyze(source), analyze(candidate)
    if after["summary"]["high"] > before["summary"]["high"]:
        return {"ok": False, "text": candidate,
                "reason": "候选引入了新的高优先级表达问题"}
    similarity = difflib.SequenceMatcher(None, source, candidate).ratio()
    score = (before["summary"]["findings"] - after["summary"]["findings"]) * 8
    score += similarity * 2 - abs(1 - ratio) * 2
    return {"ok": True, "text": candidate, "score": score,
            "reason": "已生成保真修改，请人工核对原意与上下文",
            "guard": comparison}


def _selected_window(text: str, finding: Dict) -> Tuple[int, int]:
    """Keep a selected edit inside its source line and near its finding."""
    start, end = finding["start"], finding["end"]
    line_start = text.rfind("\n", 0, start) + 1
    next_newline = text.find("\n", end)
    line_end = len(text) if next_newline < 0 else next_newline
    if line_end - line_start <= 3500:
        return line_start, line_end
    left = max(line_start, start - 1200)
    right = min(line_end, max(end + 1200, left + 2400))
    return left, right


def _difference_touches_target(source: str, candidate: str,
                               target_start: int, target_end: int) -> bool:
    for kind, left_start, left_end, _, _ in difflib.SequenceMatcher(
            None, source, candidate).get_opcodes():
        if kind == "equal":
            continue
        if (left_start < target_end and left_end > target_start
                or left_start == left_end and target_start <= left_start <= target_end):
            return True
    return False


def _deterministic_selected_text(text: str, finding: Dict) -> Optional[str]:
    """Return a guarded, exact selected edit when no model judgment is needed."""
    start, end = finding["start"], finding["end"]
    replacement = finding.get("replacement")
    if finding.get("handling") == "safe" and isinstance(replacement, str):
        output = text[:start] + replacement + text[end:]
    elif finding.get("pattern_id") == "EN-S01":
        result = edit_review_finding(text, finding)
        output = result["text"]
    elif finding.get("pattern_id") == "EN-S11":
        stripped = bilingual_rewrite._strip_en_s11_shell(text[start:])
        output = text[:start] + stripped if stripped is not None else text
    else:
        return None
    if output == text:
        return None
    comparison = _document_guard(text, output)
    if (comparison.get("fabricated") or comparison.get("n_removed")
            or comparison.get("terms_lost") or comparison.get("semantic_changed")
            or humanizer_cn._anchor_warnings(text, output)):
        return None
    return output


def deterministic_edit_target(text: str, target: Dict) -> bool:
    finding = find_edit_target(text, target)
    return bool(finding and _deterministic_selected_text(text, finding))


def edit_selected_finding(text: str, target: Dict, client: Optional[Client] = None,
                          n_candidates: int = 2) -> Dict:
    """Edit any current finding; return review advice only after the attempt."""
    finding = find_edit_target(text, target)
    if finding is None:
        raise ValueError("诊断项与当前正文不一致，请重新分析后再试。")
    before = analyze(text)
    deterministic = _deterministic_selected_text(text, finding)
    records: List[Dict] = []
    reason_code = "guard_rejected"
    reason = "没有通过事实守卫的有效修改，原文保持不变；请人工核对。"
    reason_en = ("No safe edit was accepted. The original remains unchanged; "
                 "please review this finding manually.")
    if deterministic is not None:
        output = deterministic
        reason_code = "deterministic_edit"
        reason = "已完成定向修改；请核对事实、引文与上下文。"
        reason_en = "The selected wording was edited. Please review facts, citations and context."
        records.append({"index": int(finding.get("paragraph") or 1) - 1,
                        "lang": finding.get("language") or "zh",
                        "accepted": True, "reason": reason,
                        "targets": [finding["pattern_id"]],
                        "original": text, "rewritten": output,
                        "candidates": []})
    else:
        if client is None or not client.configured:
            raise LLMError("此诊断项需要平台改写服务，当前服务不可用")
        left, right = _selected_window(text, finding)
        source = text[left:right]
        try:
            raw_candidates = client.complete(
                _REQUESTED_SYSTEM, _requested_prompt(source, [finding], finding),
                n=max(1, min(n_candidates, 4)), max_tokens=max(2000, len(source) * 2))
        except LLMError as exc:
            raise LLMError(f"定向修改调用失败：{exc}") from exc
        scored = [_requested_candidate(source, raw) for raw in raw_candidates]
        viable = [item for item in scored if item.get("ok")
                  and _difference_touches_target(
                      source, item["text"], finding["start"] - left,
                      finding["end"] - left)]
        if not viable:
            retry_reason = scored[0]["reason"] if scored else "没有候选"
            retry_prompt = (_requested_prompt(source, [finding], finding)
                            + "\n上次候选未被采纳：" + retry_reason
                            + "。请换一种小幅、保真且确实修改选中线索的写法。")
            retry = client.complete(_REQUESTED_SYSTEM, retry_prompt, n=1,
                                    max_tokens=max(2000, len(source) * 2))
            scored.extend(_requested_candidate(source, raw) for raw in retry)
            viable = [item for item in scored if item.get("ok")
                      and _difference_touches_target(
                          source, item["text"], finding["start"] - left,
                          finding["end"] - left)]
        viable.sort(key=lambda item: item["score"], reverse=True)
        output = text
        for candidate in viable:
            proposed = text[:left] + candidate["text"] + text[right:]
            comparison = _document_guard(text, proposed)
            if (comparison.get("fabricated") or comparison.get("n_removed")
                    or comparison.get("terms_lost")
                    or comparison.get("semantic_changed")
                    or humanizer_cn._anchor_warnings(text, proposed)):
                continue
            output = proposed
            reason_code = "model_edit"
            reason = "已修改选中表达；请人工核对事实、引文及原意。"
            reason_en = "The selected wording was edited. Please review facts, citations and meaning."
            break
        if output == text and scored:
            reason = "没有通过事实守卫的定向修改：" + scored[0]["reason"]
            reason_en = "No safe targeted edit was accepted; review this finding manually."
        records.append({"index": int(finding.get("paragraph") or 1) - 1,
                        "lang": finding.get("language") or "zh",
                        "accepted": output != text, "reason": reason,
                        "targets": [finding["pattern_id"]],
                        "original": source,
                        "rewritten": output[left:left + len(output) - len(text) + len(source)]
                        if output != text else source,
                        "candidates": [{key: value for key, value in item.items()
                                        if key != "guard"} for item in scored]})
    changed = output != text
    comparison = _document_guard(text, output)
    after = analyze(output)
    return {
        "text": output, "before": before, "after": after,
        "autofix": {"text": text, "changed": False, "log": []},
        "chunks": records, "n_chunks": 1, "n_accepted": int(changed),
        "n_safe_changes": int(bool(deterministic)
                              and finding.get("handling") == "safe"),
        "changed": changed,
        "guard": {"fabricated": comparison.get("fabricated", False),
                  "added": comparison.get("added", {}),
                  "removed": comparison.get("removed", {}),
                  "detail": guard.describe(comparison), "warnings": [],
                  "status": "review" if changed else "passed"},
        "review_target": {"pattern_id": finding["pattern_id"],
                          "start": finding["start"], "end": finding["end"],
                          "status": "changed" if changed else "unchanged",
                          "reason_code": reason_code, "reason": reason,
                          "reason_en": reason_en,
                          "manual_review_required": changed},
        "manual_review_required": changed,
        **({"no_change_reason": reason, "no_change_reason_en": reason_en}
           if not changed else {}),
        "method": "Selected finding edit + factual guard",
        "disclaimer": before["disclaimer"],
    }


def _requested_humanize(text: str, client: Client, n_candidates: int,
                        progress=None, stage=None) -> Dict:
    """A click on Rewrite attempts a visible edit for every report status."""
    before = analyze(text)
    stage1 = autofix(text)
    source = stage1["text"]
    if source != text:
        stage1_guard = _document_guard(text, source)
        if (stage1_guard.get("fabricated") or stage1_guard.get("n_removed")
                or stage1_guard.get("terms_lost")
                or stage1_guard.get("semantic_changed")
                or humanizer_cn._anchor_warnings(text, source)):
            source = text
            stage1 = {**stage1, "text": text, "changed": False,
                      "log": [{**item, "accepted": False,
                               "reason": "完整事实守卫未通过，安全清理已回滚"}
                              for item in stage1.get("log", [])]}
    chunks = humanizer_cn._chunks(source)
    editable_total = sum(bool(chunk and editable) for chunk, editable in chunks)
    if progress:
        progress(0, editable_total)
    outputs: List[str] = []
    records: List[Dict] = []
    done = 0
    for index, (chunk, editable) in enumerate(chunks):
        if not editable or not chunk.strip():
            outputs.append(chunk)
            continue
        findings = analyze(chunk)["findings"]
        direct = (bilingual_rewrite._strip_en_s11_sentences(chunk)
                  if any(item.get("pattern_id") == "EN-S11" for item in findings)
                  else None)
        if direct and direct != chunk:
            raw_candidates = [direct]
        else:
            try:
                raw_candidates = client.complete(
                    _REQUESTED_SYSTEM, _requested_prompt(chunk, findings),
                    n=max(1, min(n_candidates, 4)),
                    max_tokens=max(2000, len(chunk) * 2))
            except LLMError as exc:
                raise LLMError(f"第 {done + 1} 个文本块调用失败：{exc}") from exc
        scored = [_requested_candidate(chunk, raw) for raw in raw_candidates]
        viable = [item for item in scored if item.get("ok")]
        if not viable and not direct:
            retry_reason = scored[0]["reason"] if scored else "没有候选"
            retry_prompt = (_requested_prompt(chunk, findings)
                            + "\n上次候选未被采纳：" + retry_reason
                            + "。请尝试另一处小幅、保真且可见的表达修改。")
            retry = client.complete(_REQUESTED_SYSTEM, retry_prompt, n=1,
                                    max_tokens=max(2000, len(chunk) * 2))
            scored.extend(_requested_candidate(chunk, raw) for raw in retry)
            viable = [item for item in scored if item.get("ok")]
        best = max(viable, key=lambda item: item["score"]) if viable else None
        chosen = best["text"] if best else chunk
        outputs.append(chosen)
        records.append({"index": index, "lang": _paragraph_language(chunk),
                        "accepted": bool(best),
                        "reason": (best["reason"] if best else
                                   scored[0]["reason"] if scored else "模型未返回候选"),
                        "original": chunk, "rewritten": chosen,
                        "targets": sorted({item["pattern_id"] for item in findings}),
                        "candidates": [{key: value for key, value in item.items()
                                        if key != "guard"} for item in scored]})
        done += 1
        if progress:
            progress(done, editable_total)
    output = "".join(outputs)
    if stage:
        stage("checking")
    comparison = _document_guard(text, output)
    warnings: List[str] = []
    if (comparison.get("fabricated") or comparison.get("n_removed")
            or comparison.get("terms_lost") or comparison.get("semantic_changed")
            or humanizer_cn._anchor_warnings(text, output)):
        warnings.append("整篇事实守卫未通过，候选已回滚：" + guard.describe(comparison))
        output = source if source != text else text
        for record in records:
            if record["accepted"]:
                record["accepted"] = False
                record["rewritten"] = record["original"]
                record["reason"] = warnings[0]
        comparison = _document_guard(text, output)
    if (comparison.get("fabricated") or comparison.get("n_removed")
            or comparison.get("terms_lost") or comparison.get("semantic_changed")
            or humanizer_cn._anchor_warnings(text, output)):
        # Do not return an unsafe stage-one edit when the aggregate candidate
        # was rejected. This is especially important for inline bilingual prose.
        output = text
        comparison = _document_guard(text, text)
        for record in records:
            record["accepted"] = False
            record["rewritten"] = record["original"]
    changed = output != text
    accepted = sum(bool(item["accepted"]) for item in records)
    safe_changes = sum(int(item.get("count") or 1)
                       for item in stage1.get("log", []) if item.get("accepted"))
    if not changed:
        accepted = 0
        safe_changes = 0
    if stage:
        stage("finalizing")
    failed_reason = next((item["reason"] for item in records
                          if not item["accepted"] and item.get("reason")), "")
    no_change_reason = (
        "未找到通过事实守卫的有效修改；原文保持不变。"
        + ("原因：" + failed_reason if failed_reason else "")
        if not changed else "")
    return {
        "text": output, "before": before, "after": analyze(output),
        "autofix": stage1, "chunks": records,
        "n_chunks": editable_total, "n_accepted": accepted,
        "n_safe_changes": safe_changes, "changed": changed,
        "guard": {"fabricated": comparison.get("fabricated", False),
                  "added": comparison.get("added", {}),
                  "removed": comparison.get("removed", {}),
                  "detail": guard.describe(comparison), "warnings": warnings,
                  "status": "review" if changed or warnings else "passed"},
        "manual_review_required": changed,
        **({"no_change_reason": no_change_reason,
            "no_change_reason_en": "No safe edit was accepted; the manuscript is unchanged."}
           if not changed else {}),
        "method": "User-requested bilingual edit + factual guard",
        "disclaimer": before["disclaimer"],
    }


def _english_humanize(text: str, client: Client, n_candidates: int,
                      progress=None, auto_english: bool = False,
                      stage=None) -> Dict:
    stage1 = autofix(text)
    source = stage1["text"]
    rewritten = bilingual_rewrite.rewrite(
        source, client, n_candidates=n_candidates, coverage="targeted",
        progress=progress, english_auto=auto_english,
    )
    failed = [item for item in rewritten.get("paragraphs", [])
              if str(item.get("reason") or "").startswith("调用失败：")]
    if failed:
        raise LLMError(failed[0]["reason"])

    output = rewritten["text"]
    if stage:
        stage("checking")
    comparison = _document_guard(text, output)
    unsafe = (comparison.get("fabricated") or comparison.get("n_removed")
              or comparison.get("semantic_changed"))
    records = rewritten.get("paragraphs", [])
    warnings: List[str] = []
    if unsafe:
        detail = guard.describe(comparison)
        warnings.append("整篇事实守卫未通过，已回滚到原文：" + detail)
        output = text
        for item in records:
            if item.get("accepted"):
                item["accepted"] = False
                item["rewritten"] = item.get("original", "")
                item["reason"] = warnings[0]
        comparison = _document_guard(text, output)

    safe_changes = sum(int(item.get("count") or 0) for item in stage1.get("log", [])
                       if item.get("accepted"))

    if stage:
        stage("finalizing")
    after_report = analyze(output)

    return {
        "text": output,
        "before": stage1["before"],
        "after": after_report,
        "autofix": stage1,
        "chunks": records,
        "n_chunks": int(rewritten.get("n_targeted") or 0),
        "n_accepted": sum(1 for item in records if item.get("accepted")),
        "n_safe_changes": safe_changes,
        "changed": output != text,
        "guard": {
            "fabricated": comparison.get("fabricated", False),
            "added": comparison.get("added", {}),
            "removed": comparison.get("removed", {}),
            "detail": guard.describe(comparison),
            "warnings": warnings,
            "status": "review" if warnings or comparison.get("n_removed") else "passed",
        },
        "method": "Humanizer bilingual + deterministic guard",
        "disclaimer": stage1["before"]["disclaimer"],
    }


def _language_runs(text: str) -> List[Tuple[str, str]]:
    """Split a mixed document into newline-preserving language runs."""
    parts = re.split(r"(\n+)", text)
    runs: List[Tuple[str, str]] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("\n"):
            if runs:
                runs[-1] = (runs[-1][0], runs[-1][1] + part)
            else:
                runs.append(("raw", part))
            continue
        language = _editing_language(part)
        if runs and runs[-1][0] == language:
            runs[-1] = (language, runs[-1][1] + part)
        else:
            runs.append((language, part))
    return runs


def _auto_rewrite_candidate_count(text: str, findings: Sequence[Dict]) -> int:
    """Preflight the same protected runs and target rules used by humanize.

    This counts eligible targets, not accepted edits: candidates can still be
    rejected by the fact and semantic guards after the model runs.
    """
    total = 0
    document_offset = 0
    for language, segment in _language_runs(text):
        if language not in {"en", "zh"} or not segment.strip():
            document_offset += len(segment)
            continue
        leading_match = re.match(r"^\n+", segment)
        trailing_match = re.search(r"\n+$", segment)
        start = len(leading_match.group(0)) if leading_match else 0
        end = len(segment) - len(trailing_match.group(0)) if trailing_match else len(segment)
        core = segment[start:end]
        core_start, core_end = document_offset + start, document_offset + end
        planned = [item for item in findings
                   if item.get("language", "zh") == language
                   and core_start <= int(item.get("start") or 0)
                   and int(item.get("end") or 0) <= core_end]
        if planned:
            if language == "en":
                report = diagnose(core)
                total += sum(bool(bilingual_rewrite._english_auto_findings(report, pi))
                             for pi in range(len(split_paragraphs(core))))
            else:
                allowed = {str(item.get("pattern_id")) for item in planned}
                report = humanizer_cn.analyze(core)
                total += sum(1 for chunk, eligible in humanizer_cn._rewrite_chunks(
                    core, report["findings"], allowed_pattern_ids=allowed)
                    if eligible and chunk)
        document_offset += len(segment)
    return total


def humanize(text: str, client: Client, n_candidates: int = 2,
             progress=None, auto_english: bool = False, stage=None,
             user_requested: bool = False) -> Dict:
    if not client.configured:
        raise LLMError("未配置 LLM")
    if user_requested:
        return _requested_humanize(text, client, n_candidates,
                                   progress=progress, stage=stage)
    languages = set(_languages(text)) or {"zh"}
    has_protected_paragraph = any(
        _editing_language(paragraph.text) == "protected"
        for paragraph in split_paragraphs(text)
    )
    if languages == {"zh"} and not has_protected_paragraph:
        result = humanizer_cn.humanize(text, client, n_candidates=n_candidates,
                                       progress=progress)
        if stage:
            stage("checking")
        comparison = _document_guard(text, result["text"])
        warnings = list((result.get("guard") or {}).get("warnings") or [])
        if (comparison.get("fabricated") or comparison.get("n_removed")
                or comparison.get("semantic_changed")):
            notice = "双语事实守卫未通过，已回滚到原文：" + guard.describe(comparison)
            warnings.append(notice)
            for item in result.get("chunks", []):
                if item.get("accepted"):
                    item["accepted"] = False
                    item["rewritten"] = item.get("original", "")
                    item["reason"] = notice
            result["text"] = text
            result["n_accepted"] = 0
            comparison = _document_guard(text, text)
        if stage:
            stage("finalizing")
        result["after"] = analyze(result["text"])
        result["changed"] = result["text"] != text
        result["n_safe_changes"] = (sum(
            1 for item in (result.get("autofix") or {}).get("log", [])
            if item.get("accepted")) if result["changed"] else 0)
        result["guard"] = {
            "fabricated": comparison.get("fabricated", False),
            "added": comparison.get("added", {}),
            "removed": comparison.get("removed", {}),
            "detail": guard.describe(comparison),
            "warnings": warnings,
            "status": "review" if warnings or comparison.get("n_removed") else "passed",
        }
        return result
    if languages == {"en"}:
        return _english_humanize(text, client, n_candidates,
                                 progress=progress, auto_english=auto_english,
                                 stage=stage)

    runs = _language_runs(text)
    full_before = analyze(text)
    if progress:
        progress(0, len(runs))
    outputs: List[str] = []
    records: List[Dict] = []
    accepted = 0
    targeted = 0
    safe_changes = 0
    document_offset = 0
    for index, (language, segment) in enumerate(runs, start=1):
        if language == "raw" or not segment.strip():
            outputs.append(segment)
            document_offset += len(segment)
            continue
        # Inline bilingual prose is still fully analysed, but is not sent to
        # either monolingual rewriter.  Splitting at script boundaries can
        # detach qualifiers and citations from the claim they govern; keeping
        # the paragraph unchanged is the only rigorous default.
        if language in {"mixed", "protected"}:
            outputs.append(segment)
            document_offset += len(segment)
            if progress:
                progress(index, len(runs))
            continue
        # The legacy English code fixer intentionally strips document edges.
        # Keep separator runs outside either language engine so a mixed DOCX
        # retains its exact paragraph skeleton.
        leading_match = re.match(r"^\n+", segment)
        trailing_match = re.search(r"\n+$", segment)
        leading = leading_match.group(0) if leading_match else ""
        trailing = trailing_match.group(0) if trailing_match else ""
        start = len(leading)
        end = len(segment) - len(trailing) if trailing else len(segment)
        core = segment[start:end]
        core_start = document_offset + start
        core_end = document_offset + end
        planned = [item for item in full_before["findings"]
                   if item.get("language", "zh") == language
                   and core_start <= int(item.get("start") or 0)
                   and int(item.get("end") or 0) <= core_end]
        # A language run is not an independent document.  If the full report
        # found nothing in this run, do not let run-local first/last-paragraph
        # rules manufacture a rewrite target.
        if not planned:
            outputs.append(segment)
            document_offset += len(segment)
            if progress:
                progress(index, len(runs))
            continue
        if language == "en":
            result = _english_humanize(core, client, n_candidates,
                                       auto_english=auto_english)
        else:
            allowed = {str(item.get("pattern_id")) for item in planned}
            result = humanizer_cn.humanize(
                core, client, n_candidates=n_candidates,
                allowed_pattern_ids=allowed)
        outputs.append(leading + result["text"] + trailing)
        for item in result.get("chunks", []):
            records.append({**item, "language": language, "run": index})
        accepted += int(result.get("n_accepted") or 0)
        targeted += int(result.get("n_chunks") or 0)
        run_safe_changes = result.get("n_safe_changes")
        if run_safe_changes is None:
            run_safe_changes = sum(
                1 for item in (result.get("autofix") or {}).get("log", [])
                if item.get("accepted"))
        safe_changes += int(run_safe_changes or 0)
        document_offset += len(segment)
        if progress:
            progress(index, len(runs))

    output = "".join(outputs)
    if stage:
        stage("checking")
    comparison = _document_guard(text, output)
    warnings: List[str] = []
    if (comparison.get("fabricated") or comparison.get("n_removed")
            or comparison.get("semantic_changed")):
        warnings.append("整篇事实守卫未通过，已回滚到原文：" + guard.describe(comparison))
        output = text
        accepted = 0
        for item in records:
            if item.get("accepted"):
                item["accepted"] = False
                item["rewritten"] = item.get("original", "")
                item["reason"] = warnings[0]
        comparison = _document_guard(text, output)
    if stage:
        stage("finalizing")
    after_report = analyze(output)
    return {
        "text": output,
        "before": full_before,
        "after": after_report,
        "autofix": None,
        "chunks": records,
        "n_chunks": targeted,
        "n_accepted": accepted,
        "n_safe_changes": safe_changes,
        "changed": output != text,
        "guard": {
            "fabricated": comparison.get("fabricated", False),
            "added": comparison.get("added", {}),
            "removed": comparison.get("removed", {}),
            "detail": guard.describe(comparison),
            "warnings": warnings,
            "status": "review" if warnings or comparison.get("n_removed") else "passed",
        },
        "method": "Humanizer bilingual + deterministic guard",
        "disclaimer": full_before["disclaimer"],
    }
