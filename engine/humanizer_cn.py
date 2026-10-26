"""Humanizer-zh based editing engine for the local MVP.

This module deliberately does *not* predict an "AI percentage".  It turns the
31 Humanizer-zh checkpoints into explainable editing signals, applies a very
small set of deterministic safe edits, and uses the full upstream SKILL as the
policy for optional LLM rewriting.

The commercial promise of this layer is semantic preservation and reviewable
editing.  Detector-specific effectiveness has to be calibrated separately.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import guard
from llm import Client, LLMError


ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = Path(__file__).resolve().parent / "prompts" / "humanizer_cn_policy.md"

CATEGORY_NAMES = {
    "A": "铺垫代替陈述",
    "B": "公式化节奏",
    "C": "拔高与借权威",
    "D": "公式化排版",
    "E": "聊天与草稿残留",
    "F": "中文表达",
}


@dataclass
class Finding:
    pattern_id: str
    category: str
    category_name: str
    name: str
    severity: str
    start: int
    end: int
    matched: str
    paragraph: int
    reason: str
    suggestion: str
    handling: str = "review"       # safe / rewrite / review
    replacement: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class Pattern:
    pattern_id: str
    category: str
    name: str
    severity: str
    reason: str
    suggestion: str
    regex: Optional[str] = None
    flags: int = 0
    handling: str = "rewrite"
    replace: Optional[Callable[[re.Match], str]] = None


def _drop(_m: re.Match) -> str:
    return ""


def _group(n: int) -> Callable[[re.Match], str]:
    return lambda m: m.group(n)


# Regex rules are intentionally conservative.  A match is an editing signal,
# not proof of authorship.  Context-heavy patterns are marked review/rewrite.
PATTERNS: Sequence[Pattern] = (
    Pattern("A1", "A", "假对比", "medium",
            "“不仅是…更是…”容易用语气代替信息。",
            "两部分都有独立信息就保留；只是抬高语气时，直接写实质结论。",
            r"不仅(?:仅)?是?[^\n。！？；]{2,50}(?:更是|而且|还是)[^\n。！？；]{2,50}|不是[^\n。！？；]{2,45}而是[^\n。！？；]{2,45}"),
    Pattern("A2", "A", "戏剧性碎句", "low",
            "多个极短句可能在制造悬念，也可能是作者有意强调。",
            "只合并重复同一意思的碎句，承载新信息的短句要保留。",
            handling="review"),
    Pattern("A3", "A", "格言与伪深度", "medium",
            "抽象比喻没有增加可核对的意思。",
            "回到原文已经给出的具体判断；不要替作者猜新论点。",
            r"[^\n。！？]{1,24}(?:是|就是)[^\n。！？]{1,12}(?:的语言|的镜子|的桥梁|的钥匙|的密码)"),
    Pattern("A4", "A", "起跑式铺垫", "medium",
            "只是预告下文，没有独立信息。",
            "删掉预告，直接进入内容。",
            r"(?:接下来)?让我们(?:一起)?(?:深入)?(?:看看|探讨|了解)[^。！？]{0,35}[。！？]|(?:以下|下面)是你需要知道的[^。！？]{0,20}[。！？]",
            handling="rewrite"),
    Pattern("A5", "A", "无对象的辩护", "low",
            "先与假想读者辩论，可能掩盖真正结论。",
            "若没有真实反对意见，直接写后面的判断。",
            r"(?:不要误会|需要澄清的是|需要强调的是|值得注意的是)[，,:]") ,
    Pattern("B6", "B", "强凑三段式", "low",
            "三项并列本身不是问题；只有重复、空泛或为凑节奏时才需要改。",
            "核对每一项是否提供独立信息，不删真实功能、变量或条件。",
            handling="review"),
    Pattern("B7", "B", "句式开头复读", "low",
            "相邻句反复使用同一开头，可能显得拖沓。",
            "只在合并后不丢失动作和时间关系时处理。",
            handling="review"),
    Pattern("B8", "B", "破折号当万能连接", "low",
            "破折号反复用来制造揭晓感或掩盖分句关系。",
            "有解释、插入或转折功能就保留；否则换成明确的句法关系。",
            handling="review"),
    Pattern("B9", "B", "限定词堆叠", "medium",
            "同一句叠加多个同层次不确定表达。",
            "保留一个能准确表达证据强度的限定词。",
            handling="rewrite"),
    Pattern("B10", "B", "生造复合词", "low",
            "自造标签可能比原有定义更难理解。",
            "如果后文已经解释，可直接写已有定义；固定术语保留。",
            r"[“「『\"]?[\u4e00-\u9fff]{2,8}(?:-|\u2014)[\u4e00-\u9fff]{2,8}(?:-|\u2014)[\u4e00-\u9fff]{2,8}[”」』\"]?",
            handling="review"),
    Pattern("B11", "B", "被动与缺主语", "low",
            "施事者已知时，过多被动表达会让责任关系变模糊。",
            "只在施事者明确时改主动，不要补造“系统”“研究人员”。",
            handling="review"),
    Pattern("C12", "C", "空泛高频词", "medium",
            "词语本身不能证明来源，但空泛、重复或用词不准时可以精简。",
            "保留工程术语，只改没有独立信息的套话。",
            r"至关重要|深入探讨|全方位|多维度|持续赋能|无缝衔接|充分彰显(?:了)?|不懈追求",
            handling="rewrite", replace=lambda m: {
                "至关重要": "重要", "深入探讨": "讨论", "全方位": "",
                "多维度": "", "持续赋能": "支持", "无缝衔接": "衔接",
                "充分彰显": "体现", "充分彰显了": "体现了", "不懈追求": "追求",
            }.get(m.group(0), m.group(0))),
    Pattern("C13", "C", "意义拔高", "high",
            "“标志着新时代”等表述没有提供独立事实。",
            "删除空泛拔高，保留时间点、真实判断和后续计划。",
            r"[，,]?(?:这|该|此)?[^\n。！？]{0,12}(?:标志|象征)着[^\n。！？]{0,28}(?:新时代|新篇章|里程碑|历史跨越)[。！？]?",
            handling="rewrite"),
    Pattern("C14", "C", "模糊关联", "medium",
            "“有着密切联系”没有说明具体关系。",
            "原文已写明角色时直接表达；未写明就保留概括程度。",
            r"与[^\n。！？]{1,24}有着?(?:千丝万缕|密切|紧密|不可分割)的?联系"),
    Pattern("C15", "C", "句尾补充式拔高", "high",
            "句尾的“彰显了…追求”只重复赞美，没有新信息。",
            "删掉空泛尾巴，保留原句的功能、原因和结果。",
            r"[，,](?:从而|进而|由此)?(?:充分)?(?:彰显|凸显|体现|展现)了[^\n。！？]{0,30}(?:追求|精神|价值|重要性)[。！？]?",
            handling="rewrite"),
    Pattern("C16", "C", "宣传语", "medium",
            "极端赞美没有数据或条件支撑。",
            "保留产品真实特征，不制造性能参数或排名。",
            r"堪称[^\n。！？]{0,24}(?:天花板|巅峰|梦想天堂|终极解决方案)|颠覆性地|革命性地"),
    Pattern("C17", "C", "模糊权威背书", "high",
            "借“专家/研究表明”支撑主张，却没有可核对来源。",
            "保留原有归因和不确定性；需要出处时请作者补充，不编造机构或年份。",
            r"(?:一些|部分|众多|相关|未具名的)?(?:专家|学者|研究人员|业内人士)认为|(?:研究|数据|实践)表明"),
    Pattern("C18", "C", "回避“是/有”", "medium",
            "复杂系动词结构可能让句子堆砌。",
            "能用“是”“有”直接表达时精简，数量、比较和范围不变。",
            r"作为[^\n，。！？]{1,20}的?(?:重要)?(?:载体|组成部分|支撑|保障)|发挥着?[^\n，。！？]{0,16}作用"),
    Pattern("D19", "D", "无效粗体", "low",
            "Markdown 粗体可能是聊天输出残留，也可能用于有效导航。",
            "普通论文正文可去掉标记，但保留里面的全部内容。",
            r"\*\*([^*\n]{1,100})\*\*", handling="safe", replace=_group(1)),
    Pattern("D20", "D", "装饰性标题", "low",
            "表情符号和装饰线可能与学术文体不符。",
            "删除纯装饰符号，保留标题文字、层级和引用锚点。",
            r"(?m)^(#{1,6}\s*)?(?:(?:✨|🚀|⚠️?|💡|✅|❌|📌|📍|🔍|🔎|📝|📚|🎯|🔥|🌟|⭐|👉|🔹|🔸|▪️|▫️|◆|◇|●|○)\s*){1,4}",
            handling="safe", replace=lambda m: m.group(1) or ""),
    Pattern("D21", "D", "中文标点不一致", "low",
            "中文正文中混入英文直引号。",
            "统一为中文引号；JSON、代码和原文引语除外。",
            r"\"([^\"\n]{1,80})\"", handling="review",
            replace=lambda m: "“" + m.group(1) + "”"),
    Pattern("E22", "E", "客服腔", "medium",
            "独立文章里的问候、夸奖和收尾提议没有正文信息。",
            "删掉空问候，保留其中实际答案；邮件和客服回复除外。",
            r"(?:好问题|很高兴为你解答|希望这对你有所帮助)[！!。]?",
            handling="review", replace=_drop),
    Pattern("E23", "E", "重复免责与猜测填充", "low",
            "反复说“资料有限”不会增加证据。",
            "保留一处资料边界，不把猜测改成事实。",
            r"可用信息(?:确实)?(?:十分|比较|较为)?有限|由于资料有限，无法[^\n。！？]{0,30}"),
    Pattern("E24", "E", "首句复读标题", "low",
            "标题后第一句只是重复标题。",
            "只删无独立含义的复述，条件、定义和数据保留。",
            handling="review"),
    Pattern("E25", "E", "编辑过程残留", "medium",
            "正文在谈论上一稿或编辑动作。",
            "若不是变更日志或迁移说明，只保留最终信息。",
            r"这一段是(?:刚刚|新|后来)?(?:补充|改写|修改)的|上一稿中我们"),
    Pattern("F26", "F", "层叠的“的”", "medium",
            "多层定语使修饰关系难以辨认。",
            "拆出适用对象或谓语，保留原有修饰范围。",
            r"(?:[^\n，。！？]{1,14}的){3,}[^\n，。！？]{1,16}"),
    Pattern("F27", "F", "“进行＋动词”", "low",
            "名词化表达可能冗长，但正式语境中也可以自然存在。",
            "在不改变“正在/已完成/计划”状态的前提下改用直接动词。",
            r"进行(?:了|着)?(?:全面|深入|系统|进一步)?(?:的)?(?:分析|讨论|研究|测试|调整|优化|检查)"),
    Pattern("F28", "F", "被字句堆叠", "medium",
            "同段多个“被”字句可能隐去施事者。",
            "施事者已知时改主动，未知时保留；不把“被认为”改成确定因果。",
            handling="review"),
    Pattern("F29", "F", "四字词排比", "low",
            "四字节奏不是错误，但空泛同义堆叠会消耗注意力。",
            "保留真实约束和各项独立含义，只精简同义赞美。",
            handling="review"),
    Pattern("F30", "F", "万能背景开头", "medium",
            "“在…不断发展的背景下”可能没有独立时间或因果信息。",
            "背景没有信息就直接进入研究对象；真实变化趋势要保留。",
            r"^(?:在)?[^\n，。]{0,22}(?:不断|快速|飞速|蓬勃)(?:发展|演进|变革)的?(?:时代)?背景下[，,]",
            flags=re.M, handling="review"),
    Pattern("F31", "F", "套话收尾", "high",
            "结尾只是祝愿、等待或重复赞美，没有新信息。",
            "删除空收尾，实际结论、情绪和行动计划要保留。",
            r"(?:总而言之|综上所述)?[，,]?(?:让我们)?(?:拭目以待|共同期待)[^\n。！？]{0,24}[。！？]?\s*$",
            handling="rewrite"),
)


_SENTENCE = re.compile(r"[^\n。！？]+[。！？]?|\n")
_HEDGES = ("也许", "可能", "或许", "似乎", "大概", "在一定程度上", "某种程度上")
_CONSTRAINTS = re.compile(
    r"尚未确认|尚未|尚无|暂不|不得|不能|无法|并非|没有|未见|未观察到|未检出|未证实|"
    r"未(?!来)[\u4e00-\u9fff]{1,5}|缺乏|尚缺|不足以|不具备|否认|排除|"
    r"无(?:统计学|临床)?意义|"
    r"无(?:显著|明显|直接|足够|充分|证据|差异|改善|变化|影响|关联|关系|效应|作用|结果|数据|支持)|"
    r"无(?!锡|论|疑|穷|聊|辜|畏|暇)[\u4e00-\u9fff]{1,5}|"
    r"未(?:能|曾|完成|达到|发现|观察到|开放|发布|确认)|"
    r"(?<!更多)(?<!各种)(?<!一切)可能|也许|或许|据称|认为|计划|预计|拟于|正在|已经|已(?:完成|达到|发现|观察到|开放|发布|确认)|"
    r"只有|(?<!不)仅|至少|至多|超过|低于|高于|最早|如果|除非|"
    r"不(?:会|应|能|得|是|存在|支持|允许|开放|公开|接受|超过|低于|高于|少于|多于)"
)

_PROTECTED = re.compile(
    r"```[\s\S]*?```|~~~[\s\S]*?~~~|"
    r"\\begin\{[^}\n]+\}[\s\S]*?\\end\{[^}\n]+\}|"
    r"\\\[[\s\S]*?\\\]|\\\([^\n]*?\\\)|"
    r"<code(?:\s[^>]*)?>[\s\S]*?</code>|"
    r"(?m:(?:(?: {4}|\t)[^\n]*(?:\n|$))+)|"
    r"`[^`\n]+`|\$\$[\s\S]*?\$\$|(?<!\$)\$[^$\n]+\$(?!\$)"
)


def _protected_spans(text: str) -> List[Tuple[int, int]]:
    """Ranges that style rules and the model must leave byte-for-byte intact."""
    return [(m.start(), m.end()) for m in _PROTECTED.finditer(text)]


def _is_protected(start: int, end: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start < b and end > a for a, b in spans)


def _paragraph_index(text: str, start: int) -> int:
    return len(re.findall(r"\n\s*\n|\n", text[:start])) + 1


def _make_finding(text: str, p: Pattern, start: int, end: int,
                  matched: str, replacement: Optional[str] = None) -> Finding:
    return Finding(
        pattern_id=p.pattern_id,
        category=p.category,
        category_name=CATEGORY_NAMES[p.category],
        name=p.name,
        severity=p.severity,
        start=start,
        end=end,
        matched=matched,
        paragraph=_paragraph_index(text, start),
        reason=p.reason,
        suggestion=p.suggestion,
        handling=p.handling,
        replacement=replacement,
    )


def _regex_findings(text: str) -> List[Finding]:
    out: List[Finding] = []
    protected = _protected_spans(text)
    for p in PATTERNS:
        if not p.regex:
            continue
        for m in re.finditer(p.regex, text, p.flags):
            if _is_protected(m.start(), m.end(), protected):
                continue
            repl = p.replace(m) if p.replace else None
            out.append(_make_finding(text, p, m.start(), m.end(), m.group(0), repl))
    protected = _protected_spans(text)
    return [finding for finding in out
            if not _is_protected(finding.start, finding.end, protected)]


def _pattern(pid: str) -> Pattern:
    return next(p for p in PATTERNS if p.pattern_id == pid)


def _custom_findings(text: str) -> List[Finding]:
    out: List[Finding] = []

    # A2: three consecutive very short sentences.  Report the run once.
    sentence_spans = [(m.start(), m.end(), m.group(0).strip())
                      for m in _SENTENCE.finditer(text) if m.group(0).strip()]
    for i in range(max(0, len(sentence_spans) - 2)):
        run = sentence_spans[i:i + 3]
        if all(len(re.sub(r"[\s。！？]", "", s[2])) <= 8 for s in run):
            out.append(_make_finding(text, _pattern("A2"), run[0][0], run[-1][1],
                                     text[run[0][0]:run[-1][1]]))

    # B6: symmetrical triple enumerations are a review signal, never auto-fix.
    triple = re.compile(r"[^\n，。；：！？]{2,14}、"
                        r"[^\n，。；：！？]{2,14}"
                        r"(?:、|以及|和|与)"
                        r"[^\n，。；：！？]{2,14}")
    for m in triple.finditer(text):
        out.append(_make_finding(text, _pattern("B6"), m.start(), m.end(), m.group(0)))

    # B7: three consecutive sentences with the same two-character opener.
    for i in range(max(0, len(sentence_spans) - 2)):
        run = sentence_spans[i:i + 3]
        heads = [re.sub(r"^[\s“‘\"']+", "", s[2])[:2] for s in run]
        if heads[0] and len(set(heads)) == 1:
            out.append(_make_finding(text, _pattern("B7"), run[0][0], run[-1][1],
                                     text[run[0][0]:run[-1][1]]))

    # B8: only repetitive dashes count as a signal.
    for m in re.finditer(r"[^\n。！？]*(?:——|--)[^\n。！？]*(?:——|--)[^\n。！？]*", text):
        out.append(_make_finding(text, _pattern("B8"), m.start(), m.end(), m.group(0)))

    # B9: two or more hedges in one sentence.
    for s0, s1, sentence in sentence_spans:
        hits = [(sentence.find(h), h) for h in _HEDGES if h in sentence]
        if len(hits) >= 2:
            out.append(_make_finding(text, _pattern("B9"), s0, s1, sentence))

    # B11/F28: passive voice only becomes a signal when it stacks up.
    cursor = 0
    for para in re.split(r"(\n\s*\n|\n)", text):
        if not para or re.fullmatch(r"\n\s*\n|\n", para):
            cursor += len(para)
            continue
        hits = list(re.finditer(r"被[^\n，。！？]{1,30}", para))
        if len(hits) >= 2:
            start, end = cursor + hits[0].start(), cursor + hits[-1].end()
            out.append(_make_finding(text, _pattern("B11"), start, end, text[start:end]))
        if len(hits) >= 3:
            start, end = cursor + hits[0].start(), cursor + hits[-1].end()
            out.append(_make_finding(text, _pattern("F28"), start, end, text[start:end]))
        cursor += len(para)

    # E24: a short title immediately repeated by the opening sentence.
    lines = [(m.start(), m.end(), m.group(0).strip())
             for m in re.finditer(r"[^\n]+", text) if m.group(0).strip()]
    if len(lines) >= 2:
        title = re.sub(r"^#{1,6}\s*", "", lines[0][2]).strip(" ：:。！？")
        opening = re.sub(r"^[\s　]+", "", lines[1][2])
        if (3 <= len(title) <= 32 and not re.search(r"[。！？]$", lines[0][2])
                and opening.startswith(title) and len(opening) > len(title)):
            out.append(_make_finding(text, _pattern("E24"), lines[1][0],
                                     min(lines[1][1], lines[1][0] + len(title)),
                                     text[lines[1][0]:lines[1][0] + len(title)]))

    # F29: three four-character chunks in parallel.  Review only.
    four = re.compile(r"[\u4e00-\u9fff]{4}(?:、|,|，)"
                      r"[\u4e00-\u9fff]{4}(?:、|,|，)"
                      r"[\u4e00-\u9fff]{4}")
    for m in four.finditer(text):
        out.append(_make_finding(text, _pattern("F29"), m.start(), m.end(), m.group(0)))

    protected = _protected_spans(text)
    return [finding for finding in out
            if not _is_protected(finding.start, finding.end, protected)]


def _dedupe(findings: Iterable[Finding]) -> List[Finding]:
    seen = set()
    out = []
    for f in sorted(findings, key=lambda x: (x.start, x.end, x.pattern_id)):
        key = (f.pattern_id, f.start, f.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def anchors(text: str) -> Dict:
    facts = guard.extract(text)
    constraints = _CONSTRAINTS.findall(text)
    return {
        "numbers": sorted(facts["数字"]),
        "citations": sorted(facts["引用"]),
        "proper_names": sorted(facts["专名"] | facts["术语"]),
        "constraints": constraints,
        "counts": {
            "numbers": len(facts["数字"]),
            "citations": len(facts["引用"]),
            "proper_names": len(facts["专名"] | facts["术语"]),
            "constraints": len(constraints),
        },
    }


def analyze(text: str) -> Dict:
    text = text or ""
    fs = _dedupe(_regex_findings(text) + _custom_findings(text))
    sev = {s: sum(1 for f in fs if f.severity == s) for s in ("high", "medium", "low")}
    handling = {s: sum(1 for f in fs if f.handling == s)
                for s in ("safe", "rewrite", "review")}
    affected = sorted({f.paragraph for f in fs})
    if sev["high"] >= 2 or (sev["high"] + sev["medium"]) >= 6:
        status, label = "needs_work", "需要重点优化"
    elif fs:
        status, label = "review", "有可优化表达"
    else:
        status, label = "clear", "未发现明显模板化表达"
    return {
        "text": text,
        "summary": {
            "n_chars": len(re.sub(r"\s", "", text)),
            "n_paragraphs": len([p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]),
            "checks": 31,
            "findings": len(fs),
            "high": sev["high"],
            "medium": sev["medium"],
            "low": sev["low"],
            "safe_fixes": handling["safe"],
            "rewrite_items": handling["rewrite"],
            "review_items": handling["review"],
            "affected_paragraphs": len(affected),
            "status": status,
            "status_label": label,
        },
        "findings": [f.to_dict() for f in fs],
        "anchors": anchors(text),
        "categories": CATEGORY_NAMES,
        "disclaimer": (
            "这些是可核对的表达问题，不是 AI 率，也不证明文本由谁撰写。"
            "检测器效果需按平台、版本和文体另行校准。"
        ),
    }


def _tidy(text: str) -> str:
    # Replacements are deliberately exact.  Global whitespace/punctuation
    # cleanup can corrupt Python indentation, formulas and author formatting.
    return text


def autofix(text: str, allowed_pattern_ids: Optional[set] = None) -> Dict:
    """Apply only edits whose replacement is deterministic and meaning-free."""
    before = analyze(text)
    candidates = [f for f in before["findings"]
                  if f["handling"] == "safe" and f.get("replacement") is not None
                  and (allowed_pattern_ids is None
                       or f["pattern_id"] in allowed_pattern_ids)]
    if not candidates:
        # The common case for plain academic prose.  Running the full document
        # guard here would segment and align thousands of clauses even though
        # no byte changed (about 12 seconds at the 120k local limit).
        unchanged = guard.compare("", "")
        return {
            "text": text,
            "changed": False,
            "log": [],
            "before": before,
            "after": before,
            "guard": unchanged,
        }
    cur = text
    log: List[Dict] = []
    occupied_start = len(text) + 1
    for f in sorted(candidates, key=lambda x: (x["start"], x["end"]), reverse=True):
        if f["end"] > occupied_start:
            continue
        # Apply offsets from right to left, then run one document-level guard.
        # Comparing the whole document after every tiny replacement makes a
        # repeated phrase quadratic (and previously timed out on 5k chars).
        cur = cur[:f["start"]] + f["replacement"] + cur[f["end"]:]
        occupied_start = f["start"]
        log.append({"pattern_id": f["pattern_id"], "name": f["name"],
                    "accepted": True, "before": f["matched"],
                    "after": f["replacement"]})
    cur = _tidy(cur)
    final_guard = guard.compare(text, cur)
    # Final belt-and-braces check: if tidying unexpectedly changed a fact, keep original.
    if (final_guard["fabricated"] or final_guard["n_removed"]
            or final_guard.get("semantic_changed")):
        for item in log:
            item["accepted"] = False
            item["reason"] = "整体事实守卫未通过，未应用"
        return {
            "text": text,
            "changed": False,
            "log": log + [{"accepted": False, "name": "整体回滚",
                           "reason": guard.describe(final_guard)}],
            "before": before,
            "after": before,
            "guard": final_guard,
        }
    return {
        "text": cur,
        "changed": cur != text,
        "log": list(reversed(log)),
        "before": before,
        "after": analyze(cur),
        "guard": final_guard,
    }


def _skill_text() -> str:
    # 使用精简、可版本化的产品政策，而不是在每个文本块前重复塞入
    # 上游 400+ 行全文。当前命中的规则说明会由 _build user 部分定向注入。
    if not POLICY_PATH.exists():
        raise RuntimeError(f"找不到 Humanizer-zh 产品政策：{POLICY_PATH}")
    return POLICY_PATH.read_text(encoding="utf-8")


SYSTEM_SUFFIX = r"""

## 平台执行约束（优先级高于风格偏好）

你正在编辑学生自己撰写的学术文本。你只能删除空话、合并重复或重组已有信息：
1. 不增加事实、数字、参考文献、实验过程、主观经历或性能结论。
2. 保留全部数字、专名、引用、否定、限定、时间、范围、条件、归因和计划状态。
3. 不得为了“更像人”故意制造错别字、语病或虚假细节。
4. 原文已经清楚的句子原样保留。三项真实功能、变量或步骤不能为了打破并列而删除。
5. 不解释你的工作，只输出改写后正文，不要 Markdown 围栏、标题或前后言。
"""


def _clean_model_output(raw: str) -> str:
    t = (raw or "").strip()
    t = re.sub(r"^```(?:text|markdown|md)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    t = re.sub(r"^(?:改写后(?:的)?(?:正文|文本)?|优化后(?:的)?(?:正文|文本)?)\s*[:：]\s*", "", t)
    return t.strip()


def _anchor_warnings(src: str, out: str) -> List[str]:
    a, b = anchors(src), anchors(out)
    warnings = []
    for key, label in (("constraints", "否定/限定/状态词"),
                       ("numbers", "数字"), ("citations", "引用")):
        missing = list(a[key])
        for item in b[key]:
            if item in missing:
                missing.remove(item)
        if missing:
            warnings.append(f"{label}需复核：" + "、".join(missing[:8]))
    return warnings


def _paragraph_safety_error(src: str, out: str) -> Optional[Dict]:
    """Validate every source/output paragraph pair independently.

    A document-level comparison cannot see that a sentence was moved across a
    paragraph boundary: the same facts still exist somewhere in the document.
    That is unsafe for DOCX export, where paragraph N is written back into the
    original paragraph-N XML node.  Keep the exact newline skeleton, then run
    the same fact, semantic and anchor checks on each corresponding text span.
    """
    src_breaks = re.findall(r"\n+", src)
    out_breaks = re.findall(r"\n+", out)
    if src_breaks != out_breaks:
        return {"score": -8_500, "reason": "段落/换行结构发生变化"}

    src_paragraphs = re.split(r"\n+", src)
    out_paragraphs = re.split(r"\n+", out)
    if len(src_paragraphs) != len(out_paragraphs):
        # Defensive fallback: equal separator runs should imply equal lengths.
        return {"score": -8_500, "reason": "段落数量发生变化"}

    def sentence_units(value: str) -> List[str]:
        units = re.findall(r'[^\n。！？!?]+(?:[。！？!?]+|$)', value)
        return [re.sub(r'\s+|[^一-鿿a-z0-9]', '', item.lower())
                for item in units
                if len(re.sub(r'\s+|[^一-鿿a-z0-9]', '', item.lower())) >= 6]

    # Catch a sentence whose newline was moved while the document-level text
    # still contains all of the same generic words.  Ignore source sentences
    # already duplicated in another paragraph, otherwise deleting one genuine
    # duplicate would look like a cross-paragraph move.
    source_units = [sentence_units(p) for p in src_paragraphs]
    output_units = [sentence_units(p) for p in out_paragraphs]
    ownership: Dict[str, set] = {}
    for paragraph_index, units in enumerate(source_units):
        for unit in units:
            ownership.setdefault(unit, set()).add(paragraph_index)
    for paragraph_index, units in enumerate(source_units):
        own_output = output_units[paragraph_index]
        other_output = [unit for i, group in enumerate(output_units)
                        if i != paragraph_index for unit in group]
        for unit in units:
            if len(ownership.get(unit, ())) != 1:
                continue
            kept_here = any(difflib.SequenceMatcher(None, unit, item).ratio() >= 0.72
                            for item in own_output)
            found_elsewhere = any(
                difflib.SequenceMatcher(None, unit, item).ratio() >= 0.82
                or unit in item or item in unit
                for item in other_output)
            if not kept_here and found_elsewhere:
                return {
                    "score": -8_475,
                    "reason": f"第 {paragraph_index + 1} 段的句子被移到了其他段落",
                }

    for index, (before, after) in enumerate(
            zip(src_paragraphs, out_paragraphs), start=1):
        if before == after:
            continue
        if bool(before.strip()) != bool(after.strip()):
            return {
                "score": -8_450,
                "reason": f"第 {index} 段被清空或插入了跨段内容",
            }
        protected_before = [m.group(0) for m in _PROTECTED.finditer(before)]
        protected_after = [m.group(0) for m in _PROTECTED.finditer(after)]
        if protected_before != protected_after:
            return {
                "score": -8_400,
                "reason": f"第 {index} 段的代码或公式内容发生变化",
            }

        local = guard.compare(before, after)
        if local["fabricated"] or local.get("semantic_changed") or local["n_removed"]:
            return {
                "score": -8_300,
                "reason": f"第 {index} 段独立事实守卫未通过：{guard.describe(local)}",
                "guard": local,
            }
        warnings = _anchor_warnings(before, after)
        if warnings:
            return {
                "score": -8_250,
                "reason": f"第 {index} 段" + "；".join(warnings),
                "guard": local,
                "warnings": warnings,
            }
    return None


def _restore_paragraph_separators(src: str, out: str) -> str:
    """Keep the source newline skeleton when only separator widths differ.

    Models often turn single newlines into blank lines.  Reattach the exact
    source separators only if both drafts have the same nonempty paragraph
    slots.  The usual per-paragraph and fact guards still validate the text
    after this formatting-only normalization.
    """
    source_breaks = re.findall(r"\n+", src)
    output_breaks = re.findall(r"\n+", out)
    if (not source_breaks or source_breaks == output_breaks
            or len(source_breaks) != len(output_breaks)):
        return out
    source_parts = re.split(r"\n+", src)
    output_parts = re.split(r"\n+", out)
    if (len(source_parts) != len(output_parts)
            or any(not part.strip() for part in source_parts + output_parts)):
        return out
    return "".join(part + separator for part, separator in
                   zip(output_parts, source_breaks)) + output_parts[-1]


def _candidate(src: str, raw: str,
               allowed_pattern_ids: Optional[set] = None) -> Dict:
    text = _restore_paragraph_separators(src, _clean_model_output(raw))
    if not text:
        return {"ok": False, "text": src, "score": -10_000, "reason": "模型返回空文本"}
    ratio = len(text) / max(1, len(src))
    if ratio < 0.55 or ratio > 1.45:
        return {"ok": False, "text": text, "score": -9_000,
                "reason": f"长度异常（原文的 {ratio:.0%}）"}
    paragraph_error = _paragraph_safety_error(src, text)
    if paragraph_error:
        return {"ok": False, "text": text, **paragraph_error}
    protected_before = [m.group(0) for m in _PROTECTED.finditer(src)]
    protected_after = [m.group(0) for m in _PROTECTED.finditer(text)]
    if protected_before != protected_after:
        return {"ok": False, "text": text, "score": -8_400,
                "reason": "代码或公式内容发生变化"}
    cmp = guard.compare(src, text)
    if cmp["fabricated"]:
        return {"ok": False, "text": text, "score": -8_000,
                "reason": guard.describe(cmp), "guard": cmp}
    if cmp.get("semantic_changed"):
        return {"ok": False, "text": text, "score": -7_500,
                "reason": guard.describe(cmp), "guard": cmp}
    if cmp["n_removed"]:
        return {"ok": False, "text": text, "score": -7_000,
                "reason": guard.describe(cmp), "guard": cmp}
    warnings = _anchor_warnings(src, text)
    if warnings:
        return {"ok": False, "text": text, "score": -6_500,
                "reason": "；".join(warnings), "guard": cmp, "warnings": warnings}

    before, after = analyze(src), analyze(text)
    before_findings = before["findings"]
    after_findings = after["findings"]
    if allowed_pattern_ids is not None:
        before_findings = [item for item in before_findings
                           if item["pattern_id"] in allowed_pattern_ids]
        after_findings = [item for item in after_findings
                          if item["pattern_id"] in allowed_pattern_ids]
    drop = len(before_findings) - len(after_findings)
    similarity = difflib.SequenceMatcher(None, src, text).ratio()
    score = drop * 8 + similarity * 2 - cmp["n_removed"] * 5 - len(warnings) * 3
    # A rewrite with no measurable benefit should not replace the author's text.
    changed = text.strip() != src.strip()
    ok = changed and drop > 0
    reason = (f"可核对表达减少 {drop} 处，文字保留度 {similarity:.0%}"
              if ok else "没有可测量改善，保留原文")
    return {
        "ok": ok,
        "text": text,
        "score": score,
        "reason": reason,
        "guard": cmp,
        "warnings": warnings,
        "drop": drop,
        "similarity": round(similarity, 4),
        "before_findings": len(before_findings),
        "after_findings": len(after_findings),
    }


def _split_editable(text: str, limit: int) -> List[Tuple[str, bool]]:
    """Batch prose near ``limit`` while keeping boundary newlines immutable."""
    out: List[Tuple[str, bool]] = []
    remaining = text
    while remaining:
        leading = re.match(r"\n+", remaining)
        if leading:
            out.append((leading.group(0), False))
            remaining = remaining[leading.end():]
            continue
        if len(remaining) <= limit:
            trailing = re.search(r"\n+$", remaining)
            body = remaining[:trailing.start()] if trailing else remaining
            if body:
                out.append((body, True))
            if trailing:
                out.append((trailing.group(0), False))
            break
        breaks = list(re.finditer(r"\n+", remaining[:limit + 1]))
        if breaks:
            boundary = breaks[-1]
            body = remaining[:boundary.start()]
            if body:
                out.append((body, True))
            out.append((boundary.group(0), False))
            remaining = remaining[boundary.end():]
            continue
        cut = max(remaining.rfind("。", 0, limit), remaining.rfind("；", 0, limit),
                  remaining.rfind("！", 0, limit), remaining.rfind("？", 0, limit))
        cut = cut + 1 if cut >= limit // 2 else limit
        out.append((remaining[:cut], True))
        remaining = remaining[cut:]
    return out


def _chunks(text: str, limit: int = 3500) -> List[Tuple[str, bool]]:
    """Return ordered (text, editable) segments whose concatenation is exact."""
    spans = [(start, end) for start, end in _protected_spans(text)
             if "\n" in text[start:end]
             or text[start:end].startswith(("```", "~~~", "$$"))]
    out: List[Tuple[str, bool]] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            out.extend(_split_editable(text[cursor:start], limit))
        out.append((text[start:end], False))
        cursor = end
    if cursor < len(text):
        out.extend(_split_editable(text[cursor:], limit))
    return out or [(text, False)]


def humanize(text: str, client: Client, n_candidates: int = 2,
             progress=None, allowed_pattern_ids: Optional[set] = None) -> Dict:
    """Safe Humanizer-zh rewrite with deterministic pre-clean and verification."""
    if not client.configured:
        raise LLMError("未配置 LLM")
    stage1 = autofix(text, allowed_pattern_ids=allowed_pattern_ids)
    original_report = stage1["before"]
    source = stage1["text"]
    chunks = _chunks(source)
    editable_total = sum(1 for chunk, editable in chunks if editable and chunk)
    outputs: List[str] = []
    records: List[Dict] = []
    system = _skill_text() + SYSTEM_SUFFIX
    if progress:
        progress(0, editable_total)
    done = 0
    for i, (chunk, editable) in enumerate(chunks):
        if not editable or not chunk:
            outputs.append(chunk)
            continue
        report = analyze(chunk)
        report_findings = report["findings"]
        if allowed_pattern_ids is not None:
            report_findings = [item for item in report_findings
                               if item["pattern_id"] in allowed_pattern_ids]
        if not report_findings:
            outputs.append(chunk)
            records.append({"index": i, "accepted": False,
                            "reason": "未发现需要改写的问题，保留原文",
                            "original": chunk, "rewritten": chunk, "candidates": []})
            done += 1
            if progress:
                progress(done, editable_total)
            continue
        compact = [
            {"pattern": f["pattern_id"], "name": f["name"],
             "matched": f["matched"], "suggestion": f["suggestion"]}
            for f in report_findings[:24]
        ]
        user = (
            "按指令保真改写下面的学术文本。问题清单只是检查线索，"
            "必须结合上下文判断；真实列举、必要限定和正常学术表达不要强改。\n\n"
            f"可核对问题线索：{compact}\n\n"
            f"必须保留的事实锚点：{anchors(chunk)}\n\n"
            "<<<TEXT>>>\n" + chunk + "\n<<<END>>>"
        )
        try:
            raw_candidates = client.complete(system, user, n=max(1, min(n_candidates, 4)),
                                               max_tokens=max(2000, len(chunk) * 2))
        except LLMError as exc:
            # Authentication, quota and transport failures are operational
            # errors, not “zero accepted candidates”.  Surface them so the job
            # cannot look successfully completed while silently doing nothing.
            raise LLMError(f"第 {done + 1} 个文本块调用失败：{exc}") from exc
        scored = [_candidate(chunk, raw, allowed_pattern_ids=allowed_pattern_ids)
                  for raw in raw_candidates]
        viable = [c for c in scored if c.get("ok")]
        best = max(viable, key=lambda c: c["score"]) if viable else None
        chosen = best["text"] if best else chunk
        outputs.append(chosen)
        records.append({
            "index": i,
            "accepted": bool(best),
            "reason": best["reason"] if best else (scored[0]["reason"] if scored else "无候选"),
            "original": chunk,
            "rewritten": chosen,
            "warnings": best.get("warnings", []) if best else [],
            "candidates": scored,
        })
        done += 1
        if progress:
            progress(done, editable_total)

    out = "".join(outputs)
    final_guard = guard.compare(text, out)
    warnings = _anchor_warnings(text, out)
    final_unsafe = (final_guard["fabricated"] or final_guard["n_removed"]
                    or final_guard.get("semantic_changed") or warnings)
    rollback_notice = None
    if final_unsafe:
        # Candidate-level checks should already catch this.  Keep a final
        # document-level circuit breaker so future chunking changes cannot
        # leak an unsafe aggregate result.
        rollback_notice = "整篇事实守卫未通过，已回滚到原文：" + guard.describe(final_guard)
        if warnings:
            rollback_notice += "；" + "；".join(warnings)
        for record in records:
            if record.get("accepted"):
                record["accepted"] = False
                record["reason"] = rollback_notice
                record["rewritten"] = record["original"]
        out = text
        records.append({
            "index": "document",
            "accepted": False,
            "reason": rollback_notice,
            "original": text,
            "rewritten": text,
            "candidates": [],
        })
        final_guard = guard.compare(text, out)
        warnings = [rollback_notice]
    return {
        "text": out,
        "before": original_report,
        "after": analyze(out),
        "autofix": stage1,
        "chunks": records,
        "n_chunks": len(records),
        "n_accepted": sum(1 for r in records if r["accepted"]),
        "guard": {
            "fabricated": final_guard["fabricated"],
            "added": final_guard["added"],
            "removed": final_guard["removed"],
            "detail": guard.describe(final_guard),
            "warnings": warnings,
            "status": "review" if warnings or final_guard["n_removed"] else "passed",
        },
        "method": "Humanizer-zh + deterministic guard",
        "disclaimer": original_report["disclaimer"],
    }
