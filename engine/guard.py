"""事实护栏：机械比对改写前后的「可核查事实」。

五份参考资料全都只在提示词里写「不要编造数据和文献」，而其中两份的**示例本身
就在编造**（AIGC-Detector-Pro 编 p 值和 Smith(2023)，thesis-optimizer 编研究过程）。
提示词约束不可靠，必须用代码卡死。

规则：
  改写后**新增**任何数字、专名、引用 → 判定为编造，候选直接作废。
  改写后**丢失**事实 → 信息损失，计入扣分（不作废，但会被更好的候选比下去）。
"""
import difflib
import re
from typing import Dict, List, Set

import jieba.posseg as pseg

# 数值是“符号 + 数字 + 单位”的原子事实。只守住裸数字会放过
# -3.2→3.2、10 mg→10 kg、10 ℃→10 ℉ 这类致命变化。
_LATIN_UNIT = r'[A-Za-zμµΩ][A-Za-z0-9μµΩ·⋅*/^+\-−⁻¹²³]{0,23}'
_ZH_UNIT = (r'人|份|例|次|项|组|个|年|月|日|小时|分钟|秒|天|周|'
            r'万元|亿元|元|平方(?:千米|米|厘米|毫米)|立方(?:米|厘米|毫米)|'
            r'千米|厘米|毫米|米|毫升|升|千克|克|毫克|微克|摩尔|毫摩尔|微摩尔|'
            r'摄氏度|华氏度')
_UNIT = (rf'%(?!\w)|‰|℃|℉|°\s*[CF]|(?:{_LATIN_UNIT})(?![A-Za-z])|'
         rf'{_ZH_UNIT}')
_ZH_DIGITS = r'〇零一二两三四五六七八九十百千万亿'
# 把科学计数法也当作一个数值原子：10⁻³、10^-3、1e-3 和
# 1×10⁻³ 不得被改成其他数量级后仍通过守卫。
_DECIMAL = r'\d+(?:[.,]\d+)*'
_POWER = r'(?:\^[+\-−]?\d+|[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)'
_SCI_NUMBER = (rf'(?:{_DECIMAL}\s*[×xX·⋅]\s*10{_POWER}'
               rf'|{_DECIMAL}(?:[eE][+\-−]?\d+|{_POWER})?)')
_NUM = re.compile(
    rf'(?<![A-Za-z0-9.])[+\-−]?{_SCI_NUMBER}(?:\s*(?:{_UNIT}))?'
    r'|[pP]\s*[<>=]\s*0?\.\d+'
    rf'|[{_ZH_DIGITS}]+\s*(?:{_ZH_UNIT})'
    rf'|第[{_ZH_DIGITS}]+'
    rf'|[{_ZH_DIGITS}]{{2,}}(?![\u4e00-\u9fff])')
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

# 语义边界不能只靠数字和专名守护。学术文本里，“可能→确定”、
# “不开放→开放”、“超过 3000→等于 3000”都是事实变化。这些标记用
# 类别而非字面比对，允许“可能”换成“也许”，但不允许整个不确定性消失。
_SEMANTIC_PATTERNS = {
    "否定": re.compile(
        r'并非|没有|尚无|无法|不得|不能|不会|不应|不可|'
        r'未见|未观察到|未检出|未证实|未(?!来)[\u4e00-\u9fff]{1,5}|'
        r'缺乏|尚缺|不足以|不具备|否认|排除(?!无论|疑问)|'
        r'无(?:统计学|临床)?意义|'
        r'无(?:显著|明显|直接|足够|充分|证据|差异|改善|变化|影响|关联|关系|效应|作用|结果|数据|支持)|'
        r'无(?!锡|论|疑|穷|聊|辜|畏|暇)[\u4e00-\u9fff]{1,5}|'
        r'不对[^\n，。！？]{0,8}(?:开放|公开)|不代表|不意味着|'
        r'未(?:经|能|完成|确认|发现|达到|提供|开始|决定|授权)|'
        r'不(?!仅|断|懈|禁|妨|时|日|由|啻|愧|惜|错|凡|料)[\u4e00-\u9fff]{1,4}'),
    "不确定性": re.compile(r'可能|也许|或许|似乎|大概|据称|尚未确认|原因不明'),
    "计划状态": re.compile(r'计划|预计|拟于|将于|尚未开始|暂定'),
    "进行状态": re.compile(r'正在|仍在|还在|尚在'),
    "完成状态": re.compile(r'已经|已完成|已通过|已发布|已确认'),
    "条件": re.compile(r'只有|除非|如果|若是|若[^\n，。！？]{0,12}(?:则|，)|在[^\n，。！？]{1,20}条件下'),
    "范围限定": re.compile(r'(?<!不)仅(?:限|适用|在|对|有|可|能)?|至少|至多|'
                         r'全部|所有|部分|多数|少数|始终|任何|均'),
    "归因": re.compile(r'研究表明|实践表明|数据表明|数据显示|结果显示|证据显示|'
                       r'声称|据称|认为|表示|指出|报告|反映|表明|显示|发现'),
    "上升趋势": re.compile(r'增加|提高|上升|增长|增强|扩大|升高|变高'),
    "下降趋势": re.compile(r'减少|降低|下降|减弱|缩小|变低'),
    "高比较": re.compile(r'高于|优于|多于|大于|超过'),
    "低比较": re.compile(r'低于|劣于|少于|小于|不足'),
    "关系动作": re.compile(
        r'影响|促进|抑制|决定|包含|属于|依赖|作用于|导致|造成|引发|'
        r'负责|用于|采用|处理|对应|承担|执行|生成|训练|部署'),
}

# 英文学术文本的语义边界不能沿用中文正则。旧实现即使收到
# ``lang="en"``，也只会切换术语丢失判据；may→确定、删掉 not、
# correlated→causes 和 plan→released 都会被放行。这里按语义类别
# 而不是按字面词形比对，允许 may/might 等同类改写，但不允许
# 整个确定程度、极性或状态消失。
_SEMANTIC_PATTERNS_EN = {
    "否定": re.compile(
        r"\b(?:never|neither|nor|without|cannot|"
        r"can(?:not|['’]t)|(?:could|would|should|must|do|does|did|is|are|was|were|"
        r"has|have|had)n['’]t|won['’]t|shan['’]t|"
        r"fail(?:s|ed)?\s+to|lack(?:s|ed|ing)?)\b"
        r"|\bnot\b(?!\s+(?:only|just|merely|simply|more\s+than|less\s+than))"
        r"|\bno\b(?!\s+(?:more|less)\s+than)", re.I),
    "不确定性": re.compile(
        r"\b(?:could\s+potentially|may\s+possibly|may|might|could|perhaps|possibly|"
        r"probably|apparently|likely|unlikely|appears?(?:\s+to)?|seems?(?:\s+to)?|"
        r"tends?(?:\s+to)?|suggests?)\b", re.I),
    "计划状态": re.compile(
        r"\b(?:plans?|planned|planning|intends?|intended|intending|aims?|aimed|aiming|"
        r"proposes?|proposed|proposing)\s+to\b"
        r"|\b(?:is|are|was|were)\s+(?:scheduled|expected|projected)\s+to\b"
        r"|\bwill\b", re.I),
    "进行状态": re.compile(
        r"\b(?:currently|ongoing|underway|in\s+progress|continues?\s+to|"
        r"(?:is|are|was|were)\s+being)\b", re.I),
    "完成状态": re.compile(
        r"\b(?:(?:has|have|had)\s+(?:been\s+)?|(?:is|are|was|were)\s+)?"
        r"(?:completed|finished|released|published|confirmed|achieved|implemented)\b",
        re.I),
    "条件": re.compile(
        r"\b(?:if|unless|provided\s+that|providing\s+that|as\s+long\s+as|"
        r"only\s+if|in\s+the\s+event\s+that|subject\s+to)\b", re.I),
    # 把范围词分成不同语义组；否则 all→some 两边都是“1 个限定词”，
    # 只比总数会漏掉实质性的范围改变。
    "全称范围": re.compile(r"\b(?:all|every|each|always)\b", re.I),
    "部分范围": re.compile(r"\b(?:some|most|many|several|(?:a\s+)?few)\b", re.I),
    "任意范围": re.compile(r"\b(?:any|either)\b", re.I),
    "唯一范围": re.compile(r"\b(?:only|solely|exclusively)\b(?!\s*[+\-−]?\d)", re.I),
    "义务强度": re.compile(r"\b(?:must|shall|required|mandatory)\b", re.I),
    "建议强度": re.compile(r"\b(?:should|recommended|advisable)\b", re.I),
    "能力或许可": re.compile(r"\b(?:can|able\s+to|permitted\s+to|allowed\s+to)\b", re.I),
    "归因": re.compile(
        r"\b(?:studies|research|data|evidence|results?)\s+"
        r"(?:show|shows|showed|suggest|suggests|suggested|indicate|indicates|indicated|"
        r"report|reports|reported|find|finds|found)\b"
        r"|\baccording\s+to\b|\b(?:was|were|is|are)\s+reported\b", re.I),
    "上升趋势": re.compile(
        r"\b(?:increase[ds]?|increasing|rise[sn]?|rose|rising|grow(?:s|th|ing|n)?|"
        r"improve[ds]?|improving|enhance[ds]?|enhancing)\b", re.I),
    "下降趋势": re.compile(
        r"\b(?:decrease[ds]?|decreasing|decline[ds]?|declining|drop(?:s|ped|ping)?|"
        r"reduce[ds]?|reducing|lower(?:s|ed|ing)?)\b", re.I),
    "高比较": re.compile(
        r"\b(?:higher|greater|more|above|superior|outperform(?:s|ed|ing)?|exceed(?:s|ed|ing)?)\b",
        re.I),
    "低比较": re.compile(
        r"\b(?:lower|less|fewer|below|inferior|underperform(?:s|ed|ing)?)\b", re.I),
    "相等比较": re.compile(r"\b(?:equal|equals|equivalent|the\s+same\s+as)\b", re.I),
    "差异比较": re.compile(r"\b(?:different|differs?|distinct)\b", re.I),
    "关系动作": re.compile(
        r"\b(?:affect(?:s|ed|ing)?|influence(?:s|d|ing)?|determine(?:s|d|ing)?|"
        r"include(?:s|d|ing)?|contain(?:s|ed|ing)?|depend(?:s|ed|ing)?\s+on|"
        r"cause(?:s|d|ing)?|lead(?:s|ing)?\s+to|led\s+to|result(?:s|ed|ing)?\s+in|"
        r"promote(?:s|d|ing)?|inhibit(?:s|ed|ing)?)\b", re.I),
}

_BOUND = re.compile(
    r'(至少|超过|高于|大于|不少于|至多|低于|小于|不超过|'
    r'等于|为|仅|只有|约|大约|接近)\s*'
    r'(\d+(?:[.,]\d+)*\s*%?)')
_CORRELATION = re.compile(r'相关|关联|有关|同时出现|共变')
_CAUSATION = re.compile(r'导致|造成|引发|使得|因此产生|是[^\n，。]{0,15}的原因')
_BOUND_EN = re.compile(
    r'\b(at\s+least|no\s+less\s+than|greater\s+than\s+or\s+equal\s+to|'
    r'at\s+most|no\s+more\s+than|less\s+than\s+or\s+equal\s+to|'
    r'more\s+than|greater\s+than|above|over|less\s+than|fewer\s+than|below|under|'
    r'equal\s+to|exactly|approximately|about|around|roughly|nearly|only)\s*'
    r'([+\-−]?\d+(?:[.,]\d+)*\s*%?)', re.I)
_BOUND_EN_KIND = {
    "at least": ">=", "no less than": ">=", "greater than or equal to": ">=",
    "at most": "<=", "no more than": "<=", "less than or equal to": "<=",
    "more than": ">", "greater than": ">", "above": ">", "over": ">",
    "less than": "<", "fewer than": "<", "below": "<", "under": "<",
    "equal to": "=", "exactly": "=", "approximately": "~", "about": "~",
    "around": "~", "roughly": "~", "nearly": "~", "only": "only:",
}
_CORRELATION_EN = re.compile(
    r'\b(?:correlat(?:e[sd]?|ed|ing|ion)|associat(?:e[sd]?|ed|ing|ion)|'
    r'relat(?:e[sd]?|ed|ing|ion)|link(?:s|ed|ing)?)\s+(?:with|to)\b', re.I)
_CAUSATION_EN = re.compile(
    r'\b(?:cause(?:s|d|ing)?|lead(?:s|ing)?\s+to|led\s+to|'
    r'result(?:s|ed|ing)?\s+in|bring(?:s|ing)?\s+about|brought\s+about|'
    r'drive(?:s|n|ing)?|drove)\b', re.I)
_COMPARATOR = re.compile(
    r'(?:<=|>=|≤|≥|＜|＞|≦|≧|<|>)\s*'
    r'(?:[+\-−]?\d+(?:[.,]\d+)*\s*%?|[A-Za-z][A-Za-z0-9_]*)')
_EQUATION = re.compile(
    r'\b[A-Za-z][A-Za-z0-9_]*\s*(?:=|≠|≈|≃|∝)\s*'
    r'[A-Za-z0-9_+\-−*/^·⋅²³⁻¹]+')
_CLAUSE = re.compile(r'[^，,；;。！？\n]+')
_LABEL = re.compile(
    r'(?<![A-Za-z])(?:方法|模型|变量|样本|方案|算法|指标|阶段|版本)?'
    r'[A-Z](?![A-Za-z])(?:组|类|型|版)?'
    r'|(?:方法|模型|变量|样本|方案|算法|指标|阶段|版本)?[甲乙丙丁戊己庚辛壬癸](?:组|类)?'
    r'|(?:实验|对照|处理|测试|训练|验证)组')
_DIRECTED = re.compile(
    r'([A-Za-z甲乙丙丁戊己庚辛壬癸]|[\u4e00-\u9fff]{2,12})'
    r'(影响|促进|抑制|决定|包含|依赖|作用于|导致|造成|引发|'
    r'负责|用于|采用|处理|对应|承担|执行|生成|训练|部署)'
    r'([A-Za-z甲乙丙丁戊己庚辛壬癸]|[\u4e00-\u9fff]{1,12})')
_LABEL_EN = re.compile(
    # Do not compile the whole pattern with ``re.I``: doing so turns ``[A-Z]``
    # into every one-letter lowercase word ("a", "I", ...), which then binds
    # unrelated quantities to bogus labels.  Only the descriptive phrases are
    # case-insensitive; the one-letter experimental labels stay uppercase.
    r'\b(?:(?i:model|method|variable|sample|group|dataset|phase|version)\s+)?[A-Z]\b'
    r'|(?i:\b(?:control|treatment|training|validation|test)\s+group\b)')
_DIRECTED_EN = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_-]*)\s+'
    r'(affect(?:s|ed)?|influence(?:s|d)?|determine(?:s|d)?|include(?:s|d)?|'
    r'contain(?:s|ed)?|cause(?:s|d)?|promote(?:s|d)?|inhibit(?:s|ed)?)\s+'
    r'([A-Za-z][A-Za-z0-9_-]*)\b', re.I)

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


def semantic_markers(text: str, lang: str = "zh") -> Dict[str, List[str]]:
    """提取不能在润色中静默改变的语义边界。

    返回列表而非 set，因为同一类标记的出现次数也有意义。
    """
    is_en = lang == "en"
    patterns = _SEMANTIC_PATTERNS_EN if is_en else _SEMANTIC_PATTERNS
    if is_en:
        bounds = []
        masked = list(text)
        for match in _BOUND_EN.finditer(text):
            phrase = re.sub(r"\s+", " ", match.group(1).lower()).strip()
            kind = _BOUND_EN_KIND[phrase]
            number = re.sub(r"\s+", "", match.group(2))
            bounds.append(f"{kind}{number}")
            # A numeric bound is one atomic fact.  Do not also interpret the
            # ``greater``/``less`` inside it as a free-standing comparison;
            # otherwise equivalent rewrites such as "at least 10" ->
            # "no less than 10" would be rejected.
            masked[match.start():match.end()] = " " * (match.end() - match.start())
        marker_text = "".join(masked)
        out = {name: [m.group(0) for m in pat.finditer(marker_text)]
               for name, pat in patterns.items()}
        out["数量边界"] = bounds
        correlation, causation = _CORRELATION_EN, _CAUSATION_EN
    else:
        out = {name: [m.group(0) for m in pat.finditer(text)]
               for name, pat in patterns.items()}
        out["数量边界"] = [f"{m.group(1)}{m.group(2).replace(' ', '')}"
                         for m in _BOUND.finditer(text)]
        correlation, causation = _CORRELATION, _CAUSATION
    out["相关性"] = [m.group(0) for m in correlation.finditer(text)]
    out["因果性"] = [m.group(0) for m in causation.finditer(text)]
    out["比较符"] = [re.sub(r"\s+", "", m.group(0))
                   for m in _COMPARATOR.finditer(text)]
    out["公式关系"] = [re.sub(r"\s+", "", m.group(0))
                     for m in _EQUATION.finditer(text)]
    return out


def _content_sequence(text: str, lang: str = "zh") -> List[str]:
    """Ordered content tokens used only to catch subject/object swaps."""
    if lang == "en":
        stop = _GENERIC_EN | _STOP_LATIN | {
            "a", "an", "of", "to", "in", "on", "at", "as", "by", "or",
            "is", "be", "do", "does", "did", "will", "may", "might", "could",
        }
        return [word.lower() for word in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", text)
                if word.lower() not in stop and len(word) >= 2]
    seq = []
    for word, flag in pseg.cut(text):
        w = word.strip().lower()
        short_entity = bool(re.fullmatch(r'[甲乙丙丁戊己庚辛壬癸a-z]', w, re.I))
        if not w or (len(w) < 2 and not short_entity) or w in _GENERIC_ZH:
            continue
        if flag.startswith(("n", "v", "a")):
            seq.append(w)
    return seq


def _local_profile(clause: str, lang: str = "zh") -> Dict:
    is_en = lang == "en"
    sem = semantic_markers(clause, lang)
    label_pattern = _LABEL_EN if is_en else _LABEL
    directed_pattern = _DIRECTED_EN if is_en else _DIRECTED
    semantic_patterns = _SEMANTIC_PATTERNS_EN if is_en else _SEMANTIC_PATTERNS
    correlation = _CORRELATION_EN if is_en else _CORRELATION
    causation = _CAUSATION_EN if is_en else _CAUSATION
    labels = sorted(set(m.group(0).lower() for m in label_pattern.finditer(clause)))
    nums = [m.group(0).replace(" ", "") for m in _NUM.finditer(clause)]
    cites = [m.group(0).strip() for m in _CITE.finditer(clause)]
    quantities = []
    def norm_argument(value: str) -> str:
        if is_en:
            return value.strip().lower()
        value = re.sub(r'(?:能够|可以|将会|会|能|可|正在|已经|进一步)+$', '', value)
        return value.replace("的", "")

    def norm_relation(value: str) -> str:
        low = value.lower()
        if not is_en:
            return value
        if re.match(r"affect|influence", low):
            return "affect"
        if re.match(r"cause", low):
            return "cause"
        if re.match(r"include|contain", low):
            return "include"
        return re.sub(r"(?:s|ed)$", "", low)

    directed = [(norm_argument(m.group(1)), norm_relation(m.group(2)),
                 norm_argument(m.group(3)))
                for m in directed_pattern.finditer(clause)]
    label_matches = list(label_pattern.finditer(clause))
    for number in _NUM.finditer(clause):
        prior = [label for label in label_matches
                 if label.end() <= number.start() and number.start() - label.end() <= 24]
        if prior:
            label = min(prior, key=lambda item: number.start() - item.end())
            quantities.append((label.group(0).lower(), number.group(0).replace(" ", "")))
    skeleton = clause.lower()
    skeleton = _NUM.sub("#", skeleton)
    skeleton = _CITE.sub("@", skeleton)
    for pattern in semantic_patterns.values():
        skeleton = pattern.sub("", skeleton)
    skeleton = correlation.sub("", skeleton)
    skeleton = causation.sub("", skeleton)
    skeleton = re.sub(r'[^a-z0-9\u4e00-\u9fff#@]+', '', skeleton)
    return {
        "text": clause,
        "labels": labels,
        "numbers": nums,
        "citations": cites,
        "quantities": quantities,
        "directed": directed,
        "semantic": sem,
        "skeleton": skeleton,
        "terms": _content_sequence(clause, lang),
    }


def _profiles(text: str, lang: str = "zh") -> List[Dict]:
    if lang == "en":
        # 只在句点后是空白/文末时切分，避免把 0.05 的小数点当句号。
        clauses = re.split(r'[,;!?]|\.(?=\s|$)', text)
    else:
        clauses = [m.group(0) for m in _CLAUSE.finditer(text)]
    return [_local_profile(clause.strip(), lang) for clause in clauses if clause.strip()]


def _profile_sensitive(profile: Dict) -> bool:
    return bool(profile["numbers"] or profile["citations"] or profile["labels"]
                or any(profile["semantic"].values()))


def _profile_score(a: Dict, b: Dict) -> float:
    ratio = difflib.SequenceMatcher(None, a["skeleton"], b["skeleton"]).ratio()
    aset, bset = set(a["terms"]), set(b["terms"])
    overlap = len(aset & bset) / max(1, len(aset | bset))
    labels_a, labels_b = set(a["labels"]), set(b["labels"])
    label_score = 0.0
    if labels_a:
        label_score = 1.5 if labels_a == labels_b else (-1.5 if labels_b else -0.6)
    return ratio + overlap + label_score


def _local_association_changes(src: str, out: str, lang: str = "zh") -> List[Dict]:
    """Bind numbers and semantic direction to the clause they describe.

    Global sets cannot distinguish “A=10, B=20” from “A=20, B=10”.  This
    conservative alignment rejects such swaps, polarity moves and subject /
    object inversions instead of presenting them as safe.
    """
    before, after = _profiles(src, lang), _profiles(out, lang)
    changes = []
    # 改写前后的事实子句通常仍在相同或相邻位置。旧实现让每个
    # before 子句与全部 after 子句做 SequenceMatcher，12 万字会变成
    # O(P²) 并卡死请求线程。按文档相对位置投影，只在附近小窗口选
    # 最佳对齐；这仍能容忍少量合句/拆句，同时把复杂度限制为 O(P·W)。
    window = 6
    before_last = max(1, len(before) - 1)
    after_last = max(0, len(after) - 1)
    for index, a in enumerate(before):
        if not _profile_sensitive(a):
            continue
        if not after:
            changes.append({"before": a["text"], "after": "", "reason": "事实子句缺失"})
            continue
        expected = round(index * after_last / before_last)
        lo = max(0, expected - window)
        hi = min(len(after), expected + window + 1)
        b = max(after[lo:hi], key=lambda item: _profile_score(a, item))
        score = _profile_score(a, b)
        reasons = []
        if score < 0.35:
            reasons.append("无法对齐事实子句")
        if a["numbers"] != b["numbers"]:
            reasons.append("数字与对象的绑定改变")
        if sorted(a["citations"]) != sorted(b["citations"]):
            reasons.append("引用与陈述的绑定改变")
        if sorted(a["quantities"]) != sorted(b["quantities"]):
            reasons.append("对象与数值/单位的绑定改变")
        if a["directed"] != b["directed"]:
            reasons.append("关系方向改变")
        # Explicit labels make the surrounding clause a fact binding.  A
        # global bag of words cannot distinguish 甲负责训练/乙负责部署 from
        # the same words with the responsibilities swapped.  Require the
        # normalized label-bearing clause to remain stable; this intentionally
        # prefers a false rejection over silently reassigning an experiment,
        # dataset, role or output.
        if a["labels"] and a["skeleton"] != b["skeleton"]:
            reasons.append("标签关联内容改变")
        for key in a["semantic"]:
            av, bv = a["semantic"][key], b["semantic"][key]
            if key in {"数量边界", "比较符", "公式关系"}:
                different = sorted(av) != sorted(bv)
            else:
                different = len(av) != len(bv)
            if different:
                reasons.append(f"{key}绑定改变")
        # Same content tokens in another order is a strong sign that the
        # actor/object relation was reversed, e.g. 教师影响学生 → 学生影响教师.
        if (len(a["terms"]) >= 2 and sorted(a["terms"]) == sorted(b["terms"])
                and a["terms"] != b["terms"]):
            reasons.append("论元顺序改变")
        if reasons:
            changes.append({"before": a["text"], "after": b["text"],
                            "reason": "、".join(dict.fromkeys(reasons))})
    return changes


def _semantic_compare(src: str, out: str, lang: str = "zh") -> Dict:
    a, b = semantic_markers(src, lang), semantic_markers(out, lang)
    changed = {}
    for key in a:
        # 普通类别只比较数量，允许同义改写；数量边界必须逐项一致。
        if key in {"数量边界", "比较符", "公式关系"}:
            if sorted(a[key]) != sorted(b[key]):
                changed[key] = {"before": a[key], "after": b[key]}
        elif len(a[key]) != len(b[key]):
            changed[key] = {"before": a[key], "after": b[key]}

    # “相关”被改成“导致”是高危定性变化，即使两边各有一个关系词也不能放行。
    relation_shift = bool(a["相关性"] and b["因果性"]
                          and len(b["因果性"]) > len(a["因果性"]))
    if relation_shift:
        changed["关系强化"] = {"before": a["相关性"], "after": b["因果性"]}
    local = _local_association_changes(src, out, lang)
    if local:
        changed["局部事实关联"] = local
    return {"before": a, "after": b, "changed": changed,
            "changed_count": len(changed), "ok": not changed}


def compare(src: str, out: str, lang: str = "zh") -> Dict:
    """返回新增（=编造）与丢失（=信息损失）的事实。

    lang 决定实义术语和语义边界用哪套判据。默认中文，
    保持旧调用点行为不变。
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
    semantic = _semantic_compare(src, out, lang)
    return {
        "added": added,
        "removed": removed,
        "n_added": sum(len(v) for v in added.values()),
        "n_removed": sum(len(v) for v in removed.values()),
        "terms_lost": terms,
        # 中文人名/机构/地名和拉丁术语一样是可核对事实。
        "fabricated": bool(added.get("数字") or added.get("引用")
                           or added.get("术语") or added.get("专名")),
        "semantic": semantic,
        "semantic_changed": not semantic["ok"],
    }


def describe(cmp: Dict) -> str:
    parts = []
    if cmp["added"]:
        parts.append("新增（疑似编造）：" +
                     "；".join(f"{k} {', '.join(v[:5])}" for k, v in cmp["added"].items()))
    if cmp["removed"]:
        parts.append("丢失：" +
                     "；".join(f"{k} {', '.join(v[:5])}" for k, v in cmp["removed"].items()))
    if cmp.get("semantic_changed"):
        parts.append("语义边界改变：" + "、".join(cmp["semantic"]["changed"].keys()))
    return " | ".join(parts) or "事实一致"
