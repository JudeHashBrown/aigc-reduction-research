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
# 拉丁「技术名词」：只认专名形态——首字母大写、全大写缩写、或含数字。
# 不能把所有英文单词都当术语：英文段落改写时每个换掉的普通词
# （use→utilize 之类）都会被判成「新增术语」，进而误判为编造，
# 把所有合法的英文候选全部判废。
_LATIN = re.compile(
    r'\b(?:'
    r'[A-Z]{2,}[A-Za-z0-9]*'                      # 全大写缩写：MAE, AUC, BERT
    r'|[A-Z][A-Za-z]*[0-9][A-Za-z0-9]*'           # 含数字的专名：PeMS04
    r'|[A-Za-z][A-Za-z0-9]*[-_][A-Za-z0-9]*[0-9][A-Za-z0-9]*'  # ResNet-50, CIFAR-10
    r'|[A-Z][a-z]{2,}'                            # 普通专名：Smith, Rajpurkar
    r')\b')
# 引用：[1] 【1】 (Smith, 2023) （张等，2024） Smith et al. (2023)
_CITE = re.compile(r'[\[【]\s*\d+(?:\s*[-–,，]\s*\d+)*\s*[\]】]'
                   r'|[(（][^)）]{0,40}?(?:19|20)\d{2}[^)）]{0,10}[)）]'
                   r'|[A-Z][A-Za-z\-\']+\s+et\s+al\.?')
_PROPER_POS = {"nr", "ns", "nt", "nz", "nrt", "nrfg"}

# 这些词形变化不算「新增事实」，避免误杀正常改写
# 句首大写的常见虚词会被上面的专名规则误收，这里排除。
_STOP_LATIN = {"the", "this", "that", "these", "those", "and", "but", "for", "our",
               "their", "its", "his", "her", "was", "were", "are", "with", "from",
               "however", "therefore", "although", "while", "when", "where", "which",
               "studies", "research", "results", "abstract", "despite", "overall",
               "conclusion", "moreover", "furthermore", "additionally", "notably",
               "first", "firstly", "second", "secondly", "finally", "thus", "hence"}


# ---------- 实义术语：补 _LATIN / _PROPER_POS 的盲区 ----------------------
#
# 原来的守卫只认三样东西：数字、专名形态的拉丁词、引用。小写技术术语完全隐形。
# 实测后果：
#   "Our approach is efficient, underscoring the importance of spatial-temporal modeling."
#   → "Our approach is efficient."        守卫：丢失 0 项，放行
#   「本文采用时空建模方法，充分说明了其有效性。」→「本文采用方法。」  同样放行
# 而 S05/S08 这类规则的改法**恰恰就是删句尾从句**，技术贡献常常写在那儿。
# 守卫放行，评分函数的 facts_lost 也是 0，这种候选反而会被优先选中。
#
# 判据不是「这个词像不像术语」——那种全局判断做不准，英文侧曾因此把每个被换掉的
# 普通词都当成新增术语，险些把所有合法英文候选判废。
# 改用**文档内独占性**：一个词如果删掉后在全文一次都不再出现，它就是承重的。
# 泛化套话（「彰显了其应用价值」里的「价值」）要么在词表里、要么会重复出现，
# 因此不会被误判。

# 通用学术名词：删掉不构成信息损失，不参与判定
_GENERIC_ZH = {
    "价值", "意义", "作用", "影响", "方面", "问题", "情况", "方式", "水平",
    "程度", "能力", "效果", "基础", "条件", "因素", "特点", "优势", "趋势",
    "内容", "结果", "过程", "方法", "研究", "分析", "工作", "领域", "背景",
    "角度", "层面", "维度", "前景", "挑战", "机遇", "重要性", "必要性",
    # L01 提示性冒号的提示语本身。删掉「一句话总结：」当然会让「总结」消失，
    # 但那是套话不是术语——不排除的话，L01 每次都会被回滚，规则等于没有。
    "总结", "小结", "结论", "核心", "关键", "重点", "原因", "答案",
    "本质", "定义", "建议", "观点", "判断", "问题", "举例", "具体",
}
_GENERIC_EN = {
    "value", "importance", "significance", "impact", "aspect", "issue", "level",
    "ability", "effect", "basis", "condition", "factor", "feature", "advantage",
    "trend", "content", "result", "process", "method", "research", "analysis",
    "work", "field", "background", "angle", "dimension", "prospect", "challenge",
    "approach", "study", "paper", "section", "system", "model", "performance",
    "which", "that", "these", "those", "there", "their", "where", "while",
    "been", "being", "have", "has", "had", "with", "from", "this", "also",
    "more", "most", "such", "than", "then", "they", "them", "when", "what",
    "into", "over", "under", "between", "through", "across", "within", "both",
}
# 实义名词词性（jieba）：普通名词、其他专名、名动词、名形词
_CONTENT_POS = {"n", "nz", "vn", "an", "ng", "nl"}


# 以这些字收尾的中文词是泛化表述，不是技术术语（「参考价值」「应用前景」）
_GENERIC_TAIL_ZH = ("价值", "意义", "作用", "能力", "水平", "程度", "效果",
                    "前景", "趋势", "影响", "特点", "优势", "重要性", "必要性")


def _terms(text: str, lang: str) -> Set[str]:
    """文中出现过的实义术语集合。

    英文侧的取舍：单凭词长判断不出术语——上一版 4 字以上全收，
    把 will/show/future/diverse 这些普通词都算成了术语。
    改用两条形态/分布判据：
      1. 连字符复合词直接收（spatial-temporal、fine-tuned），这是最可靠的术语标记；
      2. 普通词必须在源文里**出现两次以上**才算——只出现一次的词删掉多半是套话，
         而真正的技术术语会在摘要里反复出现。
    """
    if lang == "en":
        out = {w.lower() for w in re.findall(r'\b[A-Za-z]+(?:-[A-Za-z]+)+\b', text)}
        freq: Dict[str, int] = {}
        for w in re.findall(r'\b[A-Za-z]{5,}\b', text):
            wl = w.lower()
            if wl in _GENERIC_EN or wl in _STOP_LATIN:
                continue
            freq[wl] = freq.get(wl, 0) + 1
        out |= {w for w, c in freq.items() if c >= 2}
        return out
    return {w for w, f in pseg.cut(text)
            if f in _CONTENT_POS and len(w) >= 2
            and w not in _GENERIC_ZH and not w.endswith(_GENERIC_TAIL_ZH)}


def lost_terms(src: str, out: str, lang: str = "zh") -> List[str]:
    """源文里出现、改写后一次都不再出现的实义术语。

    只看「归零」，不看词频下降：改写本来就会合并重复表述。
    词表里的 AI 套话是有意要删的，不算损失。
    """
    try:
        import lexicon as LEX_ZH
        import lexicon_en as LEX_EN
        removable = {t.lower() for t in (LEX_EN if lang == "en" else LEX_ZH).ALL_TERMS}
    except Exception:
        removable = set()
    a, b = _terms(src, lang), _terms(out, lang)
    lost = a - b
    # 词表词的**子串**也不算损失：把「不可替代」换成「关键」时，
    # 「替代」当然会消失，那是这次替换的必然结果，不是信息损失。
    return sorted(t for t in lost
                  if t.lower() not in removable
                  and not any(t in r or t.lower() in r for r in removable))


def extract(text: str) -> Dict[str, Set[str]]:
    nums = {n.replace(" ", "") for n in _NUM.findall(text)}
    latin = {w for w in _LATIN.findall(text) if w.lower() not in _STOP_LATIN}
    cites = {c.strip() for c in _CITE.findall(text)}
    proper = {w for w, f in pseg.cut(text) if f in _PROPER_POS and len(w) > 1}
    return {"数字": nums, "术语": latin, "引用": cites, "专名": proper}


def compare(src: str, out: str, lang: str = "zh") -> Dict:
    """返回新增（=编造）与丢失（=信息损失）的事实。

    lang 决定实义术语用哪套判据。默认中文，保持旧调用点行为不变。
    """
    a, b = extract(src), extract(out)
    added, removed = {}, {}
    for k in a:
        new = b[k] - a[k]
        lost = a[k] - b[k]
        if new:
            added[k] = sorted(new)
        if lost:
            removed[k] = sorted(lost)
    terms = lost_terms(src, out, lang)
    if terms:
        removed["实义术语"] = terms
    return {
        "added": added,
        "removed": removed,
        "n_added": sum(len(v) for v in added.values()),
        "n_removed": sum(len(v) for v in removed.values()),
        "terms_lost": terms,
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
