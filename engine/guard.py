"""事实护栏：机械比对改写前后的「可核查事实」。

五份参考资料全都只在提示词里写「不要编造数据和文献」，而其中两份的**示例本身
就在编造**（AIGC-Detector-Pro 编 p 值和 Smith(2023)，thesis-optimizer 编研究过程）。
提示词约束不可靠，必须用代码卡死。

规则：
  改写后**新增**任何数字、专名、引用 → 判定为编造，候选直接作废。
  改写后**丢失**事实 → 信息损失，计入扣分（不作废，但会被更好的候选比下去）。
"""
import re
from typing import Dict, List, Set

import jieba.posseg as pseg

# 数字：阿拉伯数字、百分比、p 值、区间、中文数词
_NUM = re.compile(r'\d+(?:[.,]\d+)*\s*%?|[pP]\s*[<>=]\s*0?\.\d+'
                  r'|[〇零一二三四五六七八九十百千万亿]{2,}')
# 拉丁技术名词：模型名、数据集名、缩写（ResNet-50、CIFAR-10、MAE、BERT）
_LATIN = re.compile(r'[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*')
# 引用：[1] 【1】 (Smith, 2023) （张等，2024） Smith et al. (2023)
_CITE = re.compile(r'[\[【]\s*\d+(?:\s*[-–,，]\s*\d+)*\s*[\]】]'
                   r'|[(（][^)）]{0,40}?(?:19|20)\d{2}[^)）]{0,10}[)）]'
                   r'|[A-Z][A-Za-z\-\']+\s+et\s+al\.?')
_PROPER_POS = {"nr", "ns", "nt", "nz", "nrt", "nrfg"}

# 这些词形变化不算「新增事实」，避免误杀正常改写
_STOP_LATIN = {"i", "a", "the", "of", "in", "and", "or", "to", "is", "are", "was",
               "were", "be", "it", "this", "that", "we", "our", "for", "on", "with",
               "as", "by", "at", "an", "not", "but", "its", "has", "have", "can"}


def extract(text: str) -> Dict[str, Set[str]]:
    nums = {n.replace(" ", "") for n in _NUM.findall(text)}
    latin = {w for w in _LATIN.findall(text) if w.lower() not in _STOP_LATIN and len(w) > 1}
    cites = {c.strip() for c in _CITE.findall(text)}
    proper = {w for w, f in pseg.cut(text) if f in _PROPER_POS and len(w) > 1}
    return {"数字": nums, "术语": latin, "引用": cites, "专名": proper}


def compare(src: str, out: str) -> Dict:
    """返回新增（=编造）与丢失（=信息损失）的事实。"""
    a, b = extract(src), extract(out)
    added, removed = {}, {}
    for k in a:
        new = b[k] - a[k]
        lost = a[k] - b[k]
        if new:
            added[k] = sorted(new)
        if lost:
            removed[k] = sorted(lost)
    return {
        "added": added,
        "removed": removed,
        "n_added": sum(len(v) for v in added.values()),
        "n_removed": sum(len(v) for v in removed.values()),
        "fabricated": bool(added.get("数字") or added.get("引用") or added.get("术语")),
    }


def describe(cmp: Dict) -> str:
    parts = []
    if cmp["added"]:
        parts.append("新增（疑似编造）：" +
                     "；".join(f"{k} {', '.join(v[:5])}" for k, v in cmp["added"].items()))
    if cmp["removed"]:
        parts.append("丢失：" +
                     "；".join(f"{k} {', '.join(v[:5])}" for k, v in cmp["removed"].items()))
    return " | ".join(parts) or "事实一致"
