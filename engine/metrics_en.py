"""英文侧统计指标。

阈值来自 AIGC-Detector-Pro 的 English-Specific Thresholds（无出处，待标定）：
  被动语态占比  人类 <30% / AI 可疑 >45%
  对冲词密度    人类 <3%  / AI 可疑 >6%
  TTR          人类 >0.72 / AI 可疑 <0.60
  模板过渡      人类 <2/节 / AI 可疑 >4/节
"""
import math
import re
from dataclasses import dataclass, asdict
from typing import Dict, List

import lexicon_en as LEX

THRESHOLDS_EN = {
    "passive_ratio":  {"human_max": 0.30, "ai_min": 0.45, "desc": "被动语态占比"},
    "hedge_density":  {"human_max": 0.03, "ai_min": 0.06, "desc": "对冲词密度"},
    "ttr":            {"human_min": 0.72, "ai_max": 0.60, "desc": "类符形符比 TTR"},
    "transition_density": {"human_max": 0.02, "ai_min": 0.04, "desc": "模板过渡词密度"},
    "sent_len_cv":    {"human_min": 0.25, "ai_max": 0.15, "desc": "句长变异系数"},
    "digit_density":  {"human_min": 1.2,  "ai_max": 0.4,  "desc": "数字密度(每百词)"},
}
CALIBRATED_EN = {"digit_density"}

# 启发式：be 动词 + 过去分词。会有误差，仅作参考信号。
_PASSIVE = re.compile(
    r'\b(?:is|are|was|were|be|been|being|gets?|got)\s+(?:\w+ly\s+)?'
    r'(\w+(?:ed|en|wn|ne|nt|lt|de|ught|ken|ven|own))\b', re.I)
_TRANSITIONS = ["additionally", "furthermore", "moreover", "however", "therefore",
                "consequently", "notably", "in conclusion", "overall", "firstly",
                "secondly", "finally", "in addition", "thus", "hence"]
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_NUM = re.compile(r'\d+(?:\.\d+)?%?|\bp\s*[<>=]\s*0?\.\d+', re.I)
_PROPER = re.compile(r'\b[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\b')


@dataclass
class MetricsEN:
    n_words: int
    n_sents: int
    sent_len_mean: float
    sent_len_cv: float
    passive_ratio: float
    hedge_density: float
    transition_density: float
    ttr: float
    digit_density: float
    proper_density: float

    def to_dict(self) -> Dict:
        return asdict(self)

    def flags(self, include_uncalibrated: bool = False) -> List[Dict]:
        out = []
        for key, th in THRESHOLDS_EN.items():
            if key not in CALIBRATED_EN and not include_uncalibrated:
                continue
            val = getattr(self, key, None)
            if val is None:
                continue
            ref, bad = "", False
            if "ai_max" in th and "human_min" in th and val < th["ai_max"]:
                bad, ref = True, f"低于 {th['ai_max']}（人类通常 >{th['human_min']}）"
            if "ai_min" in th and "human_max" in th and val > th["ai_min"]:
                bad, ref = True, f"高于 {th['ai_min']}（人类通常 <{th['human_max']}）"
            if bad:
                out.append({"metric": key, "desc": th["desc"],
                            "value": round(val, 4), "reference": ref})
        return out


def _cv(xs):
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    if not mean:
        return 0.0
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs)) / mean


def compute_en(text: str) -> MetricsEN:
    sents = [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    sent_word_lens = [len(_WORD.findall(s)) for s in sents] or [0]
    words = _WORD.findall(text)
    n_w = len(words) or 1
    low = text.lower()

    passive = len(_PASSIVE.findall(text))
    hedges = sum(low.count(h) for h in LEX.HEDGES)
    trans = sum(len(re.findall(r'\b' + re.escape(t) + r'\b', low)) for t in _TRANSITIONS)

    return MetricsEN(
        n_words=n_w,
        n_sents=len(sents),
        sent_len_mean=round(sum(sent_word_lens) / len(sent_word_lens), 2),
        sent_len_cv=round(_cv(sent_word_lens), 4),
        passive_ratio=round(passive / (len(sents) or 1), 4),
        hedge_density=round(hedges / n_w, 4),
        transition_density=round(trans / n_w, 4),
        ttr=round(len({w.lower() for w in words}) / n_w, 4),
        digit_density=round(len(_NUM.findall(text)) / n_w * 100, 3),
        proper_density=round(len(_PROPER.findall(text)) / n_w * 100, 3),
    )
