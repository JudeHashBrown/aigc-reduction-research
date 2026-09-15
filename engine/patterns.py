"""句式 / 段落 / 格式层的 AI 特征模式。

规则编号对照来源：
  S = 句式（thesis-optimizer L01-L07 / humanizer 模式 11-14 / 维基 AIPARALLEL,RO3,AINOCOPULA）
  P = 段落（humanizer 模式 1-2 / thesis-optimizer S01-S05）
  F = 格式（维基 AIDASH,AIBOLD,AILIST / thesis-optimizer F01-F03）

每条规则都必须能指出「命中了什么原文」——可核对是本引擎的信任基础。
"""
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


@dataclass
class Rule:
    rule_id: str
    name: str
    severity: str          # high / medium / low
    weight: float          # 临时权重，待探测标定
    explain: str
    regex: Optional[str] = None
    scope: str = "sentence"   # sentence / paragraph / document
    finder: Optional[Callable] = None   # 自定义查找器，返回 [(start, end, matched)]
    _compiled: object = field(default=None, repr=False)

    def compile(self):
        if self.regex and self._compiled is None:
            self._compiled = re.compile(self.regex)
        return self._compiled

    def find(self, text: str) -> List[Tuple[int, int, str]]:
        if self.finder:
            return self.finder(text)
        pat = self.compile()
        if not pat:
            return []
        return [(m.start(), m.end(), m.group(0)) for m in pat.finditer(text)]


# ---------- 自定义查找器 --------------------------------------------------

def find_triple_parallel(text: str) -> List[Tuple[int, int, str]]:
    """三元及以上的并列，且各项长度接近（对称感强 = AI 味重）。

    命中：「高效、鲁棒且直观」「安全性、隐私性和可靠性」「更快、更稳、更智能」
    不命中：「北京、上海和粤港澳大湾区」（各项长度参差，更像真实枚举）

    注意：第一项常带动词前缀（「保证了数据的安全性」），长度不可比，
    因此只比较第 2 项及之后的长度。
    该规则对同长度的专名枚举（如「北京、上海、广州」）会有误报，
    命中原文会完整展示给用户核对，其真实预测力待探测标定后确认。
    """
    out = []
    CONJ = '且和以及与并'
    # 以标点切成分句，在分句内部找并列，避免跨句误配
    for cm in re.finditer(r'[^，。；：！？\n]+', text):
        clause, base = cm.group(0), cm.start()
        if '、' not in clause:
            continue
        # 末项可能用连词收尾：「A、B且C」→ 统一成「A、B、C」再切分
        norm = re.sub(rf'、([^、{CONJ}]{{2,12}})[{CONJ}]([^、{CONJ}]{{2,12}})$',
                      r'、\1、\2', clause)
        items = [i for i in norm.split('、') if i]
        if len(items) < 3:
            continue
        tail = [len(i) for i in items[1:]]      # 跳过带前缀的首项
        if max(tail) - min(tail) > 2:
            continue
        if len(items[0]) < min(tail):           # 首项明显更短 → 不像并列
            continue
        out.append((base, base + len(clause), clause))
    return out


def find_hedge_stack(text: str) -> List[Tuple[int, int, str]]:
    """对冲词叠加：一句里出现 2 个以上模糊限定 = 机器式不自信。"""
    hedges = ['似乎', '可能', '或许', '大概', '在一定程度上', '某种程度上',
              '潜在', '一定的', '相对而言', '总体上']
    hits = []
    for h in hedges:
        for m in re.finditer(re.escape(h), text):
            hits.append((m.start(), m.end(), h))
    if len(hits) >= 2:
        hits.sort()
        return [(hits[0][0], hits[-1][1], '…'.join(h[2] for h in hits))]
    return []


# ---------- 句式规则 ------------------------------------------------------

SENTENCE_RULES = [
    Rule("S01", "整齐三元并列", "high", 2.5,
         "三个以上等长并列项，对称感过强。人类写作的并列项长度通常参差。",
         finder=find_triple_parallel),

    Rule("S02", "编号式枚举骨架", "high", 2.5,
         "「首先/其次/最后」「一是/二是/三是」当行文骨架。人类只在正式总结时才这样写。",
         regex=r'(首先[^。；]{0,40}[，。；][^。]{0,80}其次)'
               r'|(一是[^。；]{0,40}[，。；][^。]{0,80}二是)'
               r'|(第一[，、][^。]{0,80}第二[，、])'
               r'|(一方面[^。]{0,60}另一方面)'
               r'|(从[^，。]{1,8}(?:维度|角度|层面)(?:看|来看|出发)[^。]{0,60}从[^，。]{1,8}(?:维度|角度|层面))'),

    Rule("S03", "否定式排比", "high", 2.5,
         "「不仅…更是…」「不是…而是…」堆气势，是最典型的 AI 句式之一。",
         regex=r'(不仅(?:仅)?[^。；]{2,40}(?:更是|而且|更|还)[^。；]{2,40})'
               r'|(不(?:只|止)是[^。；]{2,40}(?:而是|更是)[^。；]{2,40})'
               r'|(并非[^。；]{2,40}而是[^。；]{2,40})'),

    Rule("S04", "回避系动词「是」", "medium", 2.0,
         "用「作为…的载体」「扮演…角色」「发挥…作用」替代直接的「是」，句子显得堆砌。",
         regex=r'(作为[^，。；]{2,20}的(?:重要)?(?:载体|组成部分|体现|基础|支撑|保障))'
               r'|(扮演(?:着)?[^，。；]{2,20}(?:的)?角色)'
               r'|(充当(?:着)?[^，。；]{2,20}(?:的)?(?:角色|功能|作用))'
               r'|(发挥(?:着)?[^，。；]{2,20}(?:的)?(?:作用|功能|价值))'
               r'|(起到了[^，。；]{2,20}(?:的)?作用)'),

    Rule("S05", "句尾浮泛分析", "high", 2.5,
         "句子末尾挂一句「从而凸显了…」「进而体现了…」，不带新信息，只制造深刻感。",
         regex=r'[，,](?:从而|进而|由此|以此)?(?:凸显|彰显|体现|印证|反映|强调|说明|展现|折射)'
               r'(?:了|出)[^。！？]{0,30}[。！？]?'),

    Rule("S06", "空心分析句式", "medium", 2.0,
         "「通过…实现…」「依托…推动…」「围绕…展开…」这类句子往往不承载具体信息。",
         regex=r'(通过[^，。；]{2,30}(?:实现|达成|完成)了?[^，。；]{2,30})'
               r'|(依托[^，。；]{2,30}推动[^，。；]{2,30})'
               r'|(围绕[^，。；]{2,30}(?:展开|进行)[^，。；]{0,20})'),

    Rule("S07", "模糊归因", "high", 3.0,
         "「专家认为」「研究表明」却不给出处。这不是学术语言，是回避引用。",
         regex=r'(?:相关)?(?:专家|学者|研究者|业内人士|相关人士|有关人士|有人|不少人)'
               r'(?:认为|指出|表示|强调|建议)'
               r'|(?:研究|数据|实践|调查)(?:表明|显示|证明|指出)'
               r'|(?:业内|学界|普遍)(?:认为|共识)'),

    Rule("S08", "泛化结尾", "high", 3.0,
         "「具有重要意义」「前景广阔」「提供了有益参考」——不说明意义是什么的空头支票。",
         regex=r'具有(?:重要|重大|深远|积极)的?[^，。；]{0,8}(?:意义|价值|作用|影响)'
               r'|前景(?:广阔|可期|值得期待)'
               r'|(?:提供|给出)了?(?:重要|有益|宝贵|有力)的?(?:参考|借鉴|启示|支撑)'
               r'|(?:指明|明确)了(?:方向|路径)'
               r'|(?:奠定|打下)了?(?:坚实)?(?:的)?基础'),

    Rule("S09", "对冲词叠加", "medium", 1.5,
         "一句里堆两个以上「似乎/可能/在一定程度上」，是机器式的过度谨慎。",
         finder=find_hedge_stack),

    Rule("S10", "疑似无主语", "low", 1.0,
         "句子直接以动词开头，缺少行为主体。启发式判断，需人工确认。",
         regex=r'^(?:具有|提供|实现|推动|体现|反映|表明|标志|形成|构建|促进|提升|优化|保障)'),
]

# ---------- 段落规则 ------------------------------------------------------

PARAGRAPH_RULES = [
    Rule("P01", "理论起笔", "medium", 1.5,
         "段落以「依据/基于 XX 理论」开头。偶尔可以，集中出现就是模板。",
         regex=r'^(?:依据|基于|根据|按照)[^，。；]{2,25}(?:理论|框架|模型|视角|范式|观点)',
         scope="paragraph"),

    Rule("P02", "段末总结套句", "high", 2.5,
         "段落收尾用「由此可见」「这一案例印证了」画蛇添足地重述一遍。",
         regex=r'(?:由此可见|综上|总的来说|总而言之|不难看出|不难发现)[^。]{0,40}[。！？]?\s*$'
               r'|(?:这|该|此)(?:一)?(?:案例|现象|结果|发现|数据)[^。]{0,10}'
               r'(?:印证|表明|说明|揭示|反映)了[^。]{0,40}[。！？]?\s*$',
         scope="paragraph"),
]

# ---------- 格式规则 ------------------------------------------------------

FORMAT_RULES = [
    Rule("F01", "破折号", "low", 0.8,
         "AI 爱用破折号制造转折。中文学术写作里密度应该很低。",
         regex=r'——|--(?!-)', scope="document"),

    Rule("F02", "正文加粗", "medium", 1.5,
         "Markdown 式加粗残留。正文全文超过 5 处即超标（humanizer-zh-academic 硬约束）。",
         regex=r'\*\*[^*\n]{1,40}\*\*', scope="document"),

    Rule("F03", "列表标记残留", "medium", 1.5,
         "行首的 -、*、•、1. 等 Markdown 列表符号，是 AI 输出直接粘贴的痕迹。",
         regex=r'(?m)^\s*(?:[-*•·]|\d+[.)、])\s+', scope="document"),

    Rule("F04", "中文里的英文引号", "low", 0.5,
         "中文正文里出现英文直引号或弯引号，通常是 AI 输出或复制残留。",
         regex=r'["“”‘’]', scope="document"),
]

ALL_RULES = SENTENCE_RULES + PARAGRAPH_RULES + FORMAT_RULES
RULES_BY_ID = {r.rule_id: r for r in ALL_RULES}

# humanizer-zh-academic 的文档级硬约束（命中即必须修复）
HARD_LIMITS = {
    "S01": ("每段", 1, "整齐三元并列每段不超过 1 处"),
    "P02": ("全文", 1, "段末总结套句全文不超过 1 处"),
    "S08": ("全文", 0, "泛化结尾必须清零"),
    "S07": ("全文", 0, "模糊归因必须清零"),
    "F02": ("全文", 5, "正文加粗不超过 5 处"),
    "P01": ("段落占比", 0.20, "以理论起笔的段落不超过 20%"),
}
