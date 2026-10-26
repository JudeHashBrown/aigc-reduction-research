"""Bilingual facade for the product editing API.

The newer product UI was originally wired only to :mod:`humanizer_cn`, while
the repository's earlier diagnostic/rewrite stack already had paragraph-level
English support.  This module keeps the stable v1 response shape and routes
each language to the engine that has actually been written and tested for it.

It deliberately reports editing signals rather than an "AI percentage".
"""
from __future__ import annotations

import re
import unicodedata
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
             progress=None, auto_english: bool = False, stage=None) -> Dict:
    if not client.configured:
        raise LLMError("未配置 LLM")
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
