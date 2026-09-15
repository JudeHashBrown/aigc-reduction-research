"""诊断主流程：切分 → 规则匹配 → 词表匹配 → 统计 → 打分 → 出报告。

设计原则：
1. 每条发现都必须带「原文片段 + 位置 + 为什么」，用户能自己核对。
   这是本产品的信任基础——我们不报一个无法验证的百分比。
2. 权重与阈值全部外置，待黑盒探测标定后替换，不改代码。
3. 段落打分沿用 humanizer-zh-academic 的确定性计分法（命中 +1，≥4 为高风险），
   同一段跑两次结果必然一致。
"""
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import lexicon as LEX
import lexicon_en as LEX_EN
import patterns as PAT
import patterns_en as PAT_EN
import metrics as MET
import metrics_en as MET_EN

SENT_END = r'[。！？；\n]'
SENT_END_EN = r'(?<=[.!?])\s+'

CJK = re.compile(r'[\u4e00-\u9fff]')
LATIN = re.compile(r'[A-Za-z]')


def detect_lang(text: str) -> str:
    """段落级语言识别。

    学位论文的典型形态是中文正文 + 英文摘要，整篇判定会让其中一种失去检测，
    所以逐段判定，各用各的规则集。
    """
    zh, en = len(CJK.findall(text)), len(LATIN.findall(text))
    if zh + en == 0:
        return "zh"
    return "zh" if zh / (zh + en) > 0.30 else "en"


@dataclass
class Span:
    text: str
    start: int          # 相对全文的字符偏移
    end: int


@dataclass
class Finding:
    rule_id: str
    name: str
    severity: str
    weight: float
    para_index: int
    sent_index: Optional[int]
    start: int
    end: int
    matched: str
    explain: str

    def to_dict(self):
        return asdict(self)


@dataclass
class ParaScore:
    index: int
    preview: str
    hit_rules: List[str]
    vocab_hits: int
    raw_score: int          # 命中特征种类数（确定性计分）
    weighted_score: float
    level: str              # high / medium / low
    lang: str = "zh"


def split_paragraphs(text: str) -> List[Span]:
    out, pos = [], 0
    for raw in text.split('\n'):
        stripped = raw.strip()
        if stripped:
            off = pos + raw.index(stripped) if stripped in raw else pos
            out.append(Span(stripped, off, off + len(stripped)))
        pos += len(raw) + 1
    return out


def split_sentences(para: Span, lang: str = "zh") -> List[Span]:
    if lang == "en":
        out, start = [], 0
        for m in re.finditer(SENT_END_EN, para.text):
            seg = para.text[start:m.start()]
            if seg.strip():
                out.append(Span(seg.strip(), para.start + start, para.start + m.start()))
            start = m.end()
        tail = para.text[start:]
        if tail.strip():
            out.append(Span(tail.strip(), para.start + start, para.start + len(para.text)))
        return out
    out, start = [], 0
    for m in re.finditer(SENT_END, para.text):
        seg = para.text[start:m.end()]
        if seg.strip():
            out.append(Span(seg.strip(), para.start + start, para.start + m.end()))
        start = m.end()
    tail = para.text[start:]
    if tail.strip():
        out.append(Span(tail.strip(), para.start + start, para.start + len(para.text)))
    return out


def _vocab_findings(sent: Span, pi: int, si: int, lang: str = "zh") -> List[Finding]:
    """词表命中。重叠时保留更长的那个（「充分说明了」优先于「充分说明」），
    避免同一处文字被重复计分。"""
    L = LEX_EN if lang == "en" else LEX
    out = []
    for term in sorted(L.ALL_TERMS, key=len, reverse=True):
        tier = L.tier_of(term)
        if tier == "T3":
            continue                      # T3 只参与密度统计，不单独报
        pat = (r'\b' + re.escape(term) + r'\b') if lang == "en" else re.escape(term)
        for m in re.finditer(pat, sent.text, re.I if lang == "en" else 0):
            sug = L.SUGGEST.get(term)
            hint = f"建议改为「{sug}」" if sug else "建议删除，或换成具体说法"
            out.append(Finding(
                rule_id=f"V-{tier}", name=f"AI 高频词（{tier}）" if lang == "zh" else f"AI vocabulary ({tier})",
                severity="high" if tier == "T1" else "medium",
                weight=L.WEIGHTS[tier], para_index=pi, sent_index=si,
                start=sent.start + m.start(), end=sent.start + m.end(),
                # 必须存原文实际命中的文字，不能存词表里的形式——
                # 英文匹配大小写不敏感，存 term 会让界面高亮与展示不一致，
                # 而「用户能自己核对」是本引擎的信任基础。
                matched=m.group(0),
                explain=(f"「{term}」是中文 AI 学术写作的高频标记。{hint}"
                         if lang == "zh"
                         else f"“{term}” is an overused AI academic marker. {hint}")))
    # 去重：丢弃被更长命中完全覆盖的短命中
    out.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: List[Finding] = []
    for f in out:
        if any(k.start <= f.start and f.end <= k.end for k in kept):
            continue
        kept.append(f)
    return kept


def diagnose(text: str, weights_path: Optional[str] = None) -> Dict:
    if weights_path and Path(weights_path).exists():
        override = json.loads(Path(weights_path).read_text(encoding="utf-8"))
        for rid, w in override.get("rules", {}).items():
            if rid in PAT.RULES_BY_ID:
                PAT.RULES_BY_ID[rid].weight = w
        LEX.WEIGHTS.update(override.get("vocab", {}))

    paras = split_paragraphs(text)
    findings: List[Finding] = []
    sent_lens, para_lens, para_heads = [], [], []
    para_sent_map: List[List[Span]] = []

    para_langs = []
    for pi, para in enumerate(paras):
        lang = detect_lang(para.text)
        para_langs.append(lang)
        sents = split_sentences(para, lang)
        para_sent_map.append(sents)
        para_lens.append(len(para.text))
        para_heads.append(para.text[:4] if lang == "zh" else para.text.split(" ")[0][:8])

        sent_rules = PAT_EN.SENTENCE_RULES_EN if lang == "en" else PAT.SENTENCE_RULES
        para_rules = PAT_EN.PARAGRAPH_RULES_EN if lang == "en" else PAT.PARAGRAPH_RULES

        for si, sent in enumerate(sents):
            sent_lens.append(len(sent.text))
            findings.extend(_vocab_findings(sent, pi, si, lang))
            for rule in sent_rules:
                for s, e, matched in rule.find(sent.text):
                    findings.append(Finding(
                        rule.rule_id, rule.name, rule.severity, rule.weight,
                        pi, si, sent.start + s, sent.start + e, matched, rule.explain))

        for rule in para_rules:
            for s, e, matched in rule.find(para.text):
                findings.append(Finding(
                    rule.rule_id, rule.name, rule.severity, rule.weight,
                    pi, None, para.start + s, para.start + e, matched, rule.explain))

    for rule in PAT.FORMAT_RULES:
        for s, e, matched in rule.find(text):
            findings.append(Finding(
                rule.rule_id, rule.name, rule.severity, rule.weight,
                -1, None, s, e, matched, rule.explain))

    zh_text = "\n".join(p.text for p, lg in zip(paras, para_langs) if lg == "zh")
    en_text = "\n".join(p.text for p, lg in zip(paras, para_langs) if lg == "en")
    zh_sent_lens = [len(x.text) for p_i, ss in enumerate(para_sent_map)
                    for x in ss if para_langs[p_i] == "zh"]
    m = MET.compute(zh_text or text,
                    zh_sent_lens or sent_lens,
                    [len(p.text) for p, lg in zip(paras, para_langs) if lg == "zh"] or para_lens,
                    [h for h, lg in zip(para_heads, para_langs) if lg == "zh"] or para_heads)
    m_en = MET_EN.compute_en(en_text) if en_text.strip() else None

    # ---- 段落打分（确定性）----
    para_scores: List[ParaScore] = []
    for pi, para in enumerate(paras):
        pf = [f for f in findings if f.para_index == pi]
        kinds = sorted({f.rule_id for f in pf})
        vocab_hits = sum(1 for f in pf if f.rule_id.startswith("V-"))
        raw = len(kinds)
        if vocab_hits > LEX.PARA_VOCAB_LIMIT:
            raw += 1                                  # 超硬约束额外记一分
        weighted = sum(f.weight for f in pf)
        level = "high" if raw >= 4 else ("medium" if raw >= 2 else "low")
        ps = ParaScore(pi, para.text[:40], kinds, vocab_hits,
                       raw, round(weighted, 2), level)
        ps.lang = para_langs[pi]
        para_scores.append(ps)

    # ---- 硬约束核查 ----
    violations = []
    for rid, (scope, limit, desc) in PAT.HARD_LIMITS.items():
        hits = [f for f in findings if f.rule_id == rid]
        if scope == "全文":
            if len(hits) > limit:
                violations.append({"rule_id": rid, "desc": desc,
                                   "actual": len(hits), "limit": limit})
        elif scope == "每段":
            for pi in range(len(paras)):
                n = sum(1 for f in hits if f.para_index == pi)
                if n > limit:
                    violations.append({"rule_id": rid, "desc": desc,
                                       "para": pi + 1, "actual": n, "limit": limit})
        elif scope == "段落占比" and paras:
            ratio = len({f.para_index for f in hits}) / len(paras)
            if ratio > limit:
                violations.append({"rule_id": rid, "desc": desc,
                                   "actual": round(ratio, 2), "limit": limit})

    # 每段 AI 高频词硬上限
    for ps in para_scores:
        if ps.vocab_hits > LEX.PARA_VOCAB_LIMIT:
            violations.append({"rule_id": "V-LIMIT",
                               "desc": f"每段 AI 高频词不超过 {LEX.PARA_VOCAB_LIMIT} 个",
                               "para": ps.index + 1, "actual": ps.vocab_hits,
                               "limit": LEX.PARA_VOCAB_LIMIT})

    findings.sort(key=lambda f: f.start)
    sev_count = {s: sum(1 for f in findings if f.severity == s)
                 for s in ("high", "medium", "low")}

    return {
        "summary": {
            # 文档级计数独立于分语言统计，否则中英混排时会只统计其中一种
            "总字数": len(re.sub(r'\s', '', text)),
            "段落数": len(paras),
            "句数": len(sent_lens),
            "检出特征总数": len(findings),
            "高风险": sev_count["high"], "中风险": sev_count["medium"],
            "低风险": sev_count["low"],
            "高风险段落": sum(1 for p in para_scores if p.level == "high"),
            "硬约束违反": len(violations),
            "语言构成": {"中文段": para_langs.count("zh"), "英文段": para_langs.count("en")},
        },
        "findings": [f.to_dict() for f in findings],
        "paragraphs": [asdict(p) for p in para_scores],
        "metrics": m.to_dict(),
        "metric_flags": m.flags(),
        "metrics_en": m_en.to_dict() if m_en else None,
        "metric_flags_en": m_en.flags() if m_en else [],
        "para_langs": para_langs,
        "hard_limit_violations": violations,
    }
