"""统计层指标。

阈值来源：AIGC-Detector-Pro 的检测指标表（无出处，标记为待标定）。
所有阈值集中在 THRESHOLDS，探测标定后整体替换。

其中「具体性」组（数字密度、专名密度、实词密度）是本项目理论的核心度量：
AI 文本的病根是具体事实被抹成笼统褒扬，这几项直接测量抹除程度。
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Dict, List

import warnings
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
import jieba
import jieba.posseg as pseg

jieba.setLogLevel(60)

# 待标定阈值：(人类正常, AI 可疑)，None 表示单侧
THRESHOLDS = {
    "sent_len_cv":      {"human_min": 0.25, "ai_max": 0.15, "desc": "句长变异系数"},
    "connective_ratio": {"human_max": 0.08, "ai_min": 0.12, "desc": "连接词密度"},
    "content_ratio":    {"human_min": 0.55, "ai_max": 0.45, "desc": "实词密度"},
    "digit_density":    {"human_min": 1.2,  "ai_max": 0.4,  "desc": "数字密度(每百字)"},
    "proper_density":   {"human_min": 1.0,  "ai_max": 0.3,  "desc": "专名密度(每百字)"},
    "ttr":              {"human_min": 0.60, "ai_max": 0.50, "desc": "类符形符比"},
    "ngram_repeat":     {"human_max": 0.03, "ai_min": 0.06, "desc": "4-gram 自相似度"},
}

# 已通过对照实验初步验证的指标；其余待黑盒探测标定后加入
CALIBRATED = {"digit_density"}

CONNECTIVES = {
    "此外", "然而", "因此", "同时", "并且", "而且", "但是", "不过", "所以",
    "从而", "进而", "由于", "因为", "如果", "虽然", "尽管", "首先", "其次",
    "最后", "另外", "总之", "综上", "可见", "基于此", "鉴于此", "与此同时",
}

CONTENT_POS = {"n", "nr", "ns", "nt", "nz", "nl", "ng",
               "v", "vd", "vn", "vf", "vx", "vi", "vl", "vg",
               "a", "ad", "an", "ag", "al", "b", "m", "q", "j", "i", "l", "s", "t"}
PROPER_POS = {"nr", "ns", "nt", "nz", "nrt", "nrfg"}

_LATIN_TERM_RE = re.compile(r'[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*')

_NUM_RE = re.compile(
    r'\d+(?:\.\d+)?%?'                       # 阿拉伯数字、小数、百分比
    r'|[〇零一二三四五六七八九十百千万亿]{2,}'   # 多位中文数字（单字「一」噪声大，排除）
    r'|[pP]\s*[<>=]\s*0?\.\d+'               # p 值
)


@dataclass
class Metrics:
    n_chars: int
    n_sents: int
    n_paras: int
    sent_len_mean: float
    sent_len_std: float
    sent_len_cv: float
    para_len_cv: float
    connective_ratio: float
    content_ratio: float
    digit_density: float
    proper_density: float
    ttr: float
    ngram_repeat: float
    para_head_repeat: float

    def to_dict(self) -> Dict:
        return asdict(self)

    def flags(self, include_uncalibrated: bool = False) -> List[Dict]:
        """返回落入「AI 可疑区间」的指标。

        未经标定的阈值默认不告警（CALIBRATED 之外的项）——在拿到黑盒探测
        数据之前，拿无出处的阈值去吓用户，和竞品编造百分比没有区别。
        """
        out = []
        for key, th in THRESHOLDS.items():
            if key not in CALIBRATED and not include_uncalibrated:
                continue
            val = getattr(self, key, None)
            if val is None:
                continue
            suspicious, ref = False, ""
            if "ai_max" in th and "human_min" in th:
                if val < th["ai_max"]:
                    suspicious, ref = True, f"低于 {th['ai_max']}（人类通常 >{th['human_min']}）"
            if "ai_min" in th and "human_max" in th:
                if val > th["ai_min"]:
                    suspicious, ref = True, f"高于 {th['ai_min']}（人类通常 <{th['human_max']}）"
            if suspicious:
                out.append({"metric": key, "desc": th["desc"],
                            "value": round(val, 4), "reference": ref})
        return out


def _cv(xs: List[int]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) / mean


def compute(text: str, sent_lens: List[int], para_lens: List[int],
            para_heads: List[str]) -> Metrics:
    words = [(w, f) for w, f in pseg.cut(text) if w.strip()]
    tokens = [w for w, _ in words]
    n_tok = len(tokens) or 1
    n_chars = len(re.sub(r'\s', '', text)) or 1

    connective = sum(1 for w in tokens if w in CONNECTIVES)
    content = sum(1 for w, f in words if f in CONTENT_POS and len(w) > 1)
    proper = sum(1 for w, f in words if f in PROPER_POS)
    # jieba 不把拉丁字母的技术名词标成专名（ResNet-50、AUC、Rajpurkar），需单独计入。
    # 这类词恰恰是「具体性」最强的证据，漏掉会严重低估人类文本。
    proper += len(_LATIN_TERM_RE.findall(text))
    digits = len(_NUM_RE.findall(text))

    # 4-gram 自相似度：重复出现的 4 字片段占比，测模板化程度
    grams = [text[i:i + 4] for i in range(max(0, len(text) - 3))]
    gram_ct = Counter(grams)
    repeated = sum(c for g, c in gram_ct.items() if c > 1 and not g.isspace())
    ngram_repeat = repeated / (len(grams) or 1)

    # 相邻段落首词雷同率：结构模板化的信号
    head_repeat = 0.0
    if len(para_heads) > 1:
        same = sum(1 for a, b in zip(para_heads, para_heads[1:]) if a and a == b)
        head_repeat = same / (len(para_heads) - 1)

    return Metrics(
        n_chars=n_chars,
        n_sents=len(sent_lens),
        n_paras=len(para_lens),
        sent_len_mean=round(sum(sent_lens) / len(sent_lens), 2) if sent_lens else 0.0,
        sent_len_std=round(_cv(sent_lens) * (sum(sent_lens) / len(sent_lens)), 2) if sent_lens else 0.0,
        sent_len_cv=round(_cv(sent_lens), 4),
        para_len_cv=round(_cv(para_lens), 4),
        connective_ratio=round(connective / n_tok, 4),
        content_ratio=round(content / n_tok, 4),
        digit_density=round(digits / n_chars * 100, 3),
        proper_density=round(proper / n_chars * 100, 3),
        ttr=round(len(set(tokens)) / n_tok, 4),
        ngram_repeat=round(ngram_repeat, 4),
        para_head_repeat=round(head_repeat, 4),
    )
