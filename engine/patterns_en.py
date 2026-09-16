"""英文侧的句式 / 段落 / 格式规则。

规则编号与中文侧一一对应（S03 中文是否定式排比，英文也是），
方便跨语言比较效应量，也方便探测实验合并分析。
"""
import re
from patterns import Rule

W = r'\b'


def find_rule_of_three(text: str):
    """Rule of three：三项等长并列（维基 WP:RO3）。

    与中文侧同理，首项常被前面的词粘连（“but also robust”），长度不可比，
    因此只比较第 2、3 项的长度。
    """
    # 末项后面的虚词会被 {0,2} 贪婪吞进来（「Carol Wang for」），
    # 既污染展示给用户的原文，也让专名判据失效。
    _TAIL = {"for", "in", "on", "to", "with", "of", "at", "by", "from",
             "and", "or", "as", "that", "which", "who", "when", "while"}

    out = []
    pat = r'\b(\w+(?:\s\w+){0,2}),\s(\w+(?:\s\w+){0,2}),\s+and\s(\w+(?:\s\w+){0,2})\b'
    for m in re.finditer(pat, text):
        g = list(m.groups())
        end = m.end()
        last = g[2].split()
        while len(last) > 1 and last[-1].lower() in _TAIL:
            end -= len(last[-1]) + 1
            last.pop()
        g[2] = " ".join(last)

        tail = [len(x.split()) for x in g[1:]]
        if max(tail) - min(tail) > 1:
            continue
        if len(g[0].split()) < min(tail):
            continue
        # 专名枚举不是文风问题：作者署名、致谢名单、数据集名单都长这样。
        # 只看第 2、3 项的首词——首项常被前面的动词粘连（「We thank Alice Chen」
        # 会捕到「thank Alice Chen」），带着它判必然失效，和上面长度比较跳过
        # 首项是同一个原因。人名、机构名、数据集名总是首字母大写。
        if all(item.split()[0][:1].isupper() for item in g[1:] if item.split()):
            continue
        out.append((m.start(), end, text[m.start():end]))
    return out


def find_hedge_stack_en(text: str):
    import lexicon_en as LEX
    hits = []
    for h in LEX.HEDGES:
        for m in re.finditer(re.escape(h), text, re.I):
            hits.append((m.start(), m.end(), h))
    if len(hits) >= 2:
        hits.sort()
        return [(hits[0][0], hits[-1][1], " … ".join(h[2] for h in hits))]
    return []


SENTENCE_RULES_EN = [
    Rule("S01", "Rule of three", "low", 0.8,
         "三项等长并列（WP:RO3）。**只报告，不自动修。**"
         "中文侧在 8 篇学术基准上抽样复核过同类规则，18 条命中约 15 条是合法的技术枚举"
         "（材料属性、法条项目、药理机制），误报率约 85%；英文侧未做同等测量，"
         "但「abnormal returns, stock liquidity, and analyst forecast accuracy」"
         "这类列举结果变量的写法同样是正常学术表达。"
         "底层特征在中文语料实测只有 1.8x，处于边缘带。",
         fix="先自己判断这三项是不是必须完整列出的材料。"
             "如果是（变量名、数据集、法条），保持原样。"
             "如果只是为了凑气势的抽象并列（「更高效、更专注、更有创造力」），"
             "改掉其中一项的句法，别让三项排成同一结构。",
         finder=find_rule_of_three),

    Rule("S03", "Negative parallelism", "high", 3.0,
         "“not just X, but Y” / “It's not X, it's Y”。维基 WP:AIPARALLEL，最典型的 AI 句式。",
         fix="State the positive claim directly. \"not just accurate, but also efficient\" → \"accurate and efficient\". Swapping in \"rather than\" is the same move, not a fix.",         regex=r'(?i)\bnot (?:just|only|merely|simply)\b[^.;!?]{2,60}?\bbut\b[^.;!?]{2,60}'
               r'|\bit(?:\'s| is| was) not\b[^.;!?]{2,50}?,?\s*(?:it(?:\'s| is)|but)\b[^.;!?]{2,50}'
               r'|\brather than\b[^.;!?]{2,50}'),

    Rule("S04", "Copula avoidance", "medium", 2.0,
         "用 serves as / stands as / represents 回避 is。维基 WP:AINOCOPULA。",
         fix="Use \"is\". \"serves as a pivotal tool\" → \"is a key tool\".",         regex=r'(?i)\b(?:serves?|serving|stands?|functions?|operates?|acts?) as\b'
               r'|\brepresents? an?\b|\bboasts?\b|\brefers to\b'),

    Rule("S05", "Superficial -ing tail", "high", 2.5,
         "句尾挂 -ing 分词短语制造深刻感（维基 WP:SUPERFICIAL），不带新信息。",
         fix="Delete the trailing -ing clause. Keep the factual first half. If the clause names a real contribution (\"underscoring the importance of spatial-temporal modeling\"), rewrite it as its own sentence instead of deleting it.",         regex=r'(?i),\s(?:highlighting|underscoring|emphasizing|showcasing|reflecting'
               r'|demonstrating|illustrating|ensuring|contributing to|fostering'
               r'|solidifying|cementing|symbolizing|marking)\b[^.;!?]{0,60}'),

    Rule("S07", "Vague attribution", "high", 3.0,
         "“experts argue” “studies show” 却不给出处。维基 WP:AIWEASEL。",
         fix="Add the actual citation, or drop the lead-in and state the claim. \"Studies show that X\" → \"X\" or \"Smith (2021) shows X\". The tool will not invent a source for you.",         regex=r'(?i)\b(?:experts?|scholars?|researchers?|observers?|critics?|analysts?|'
               r'commentators?|industry reports?|some)\s+'
               r'(?:argue|suggest|note|contend|have (?:cited|noted|argued)|believe|point out)\b'
               r'|\b(?:studies|research|evidence|data)\s+(?:show|shows|suggest|suggests|indicate|indicates)\b'
               r'|\bit is (?:widely |generally )?(?:believed|accepted|acknowledged)\b'),

    Rule("S08", "Canned significance", "high", 3.0,
         "“plays a crucial role” “is a testament to” “underscores the importance”。维基 WP:AILEGACY。",
         fix="Delete the canned phrase, keep the substance before it. \"...and interpretable, underscoring the importance of X\" → keep everything up to \"interpretable\".",         regex=r'(?i)\bplays? an? (?:crucial|vital|pivotal|key|significant|important) role\b'
               r'|\b(?:is|stands|serves) as a testament\b'
               r'|\bunderscor(?:es|ing) the (?:importance|significance|need)\b'
               r'|\bhighlights? the (?:importance|significance)\b'
               r'|\bmark(?:s|ing) a (?:pivotal|significant|key) (?:moment|shift|turning point)\b'
               r'|\bpaving the way\b|\bopens? (?:up )?new (?:avenues|possibilities|frontiers)\b'),

    Rule("S09", "Hedging stack", "medium", 1.5,
         "一句里堆两个以上对冲表达。AIGC-Detector-Pro：hedging 密度 >6% 可疑。",
         fix="Keep one hedge, drop the rest. Do not strip them all — the author's original qualifiers are their claim strength.",         finder=find_hedge_stack_en),

    Rule("S11", "Passive opener", "medium", 1.5,
         "“It was found that…” “It should be noted that…” 这类无主体被动开头。",
         fix="Name the agent. \"It was found that…\" → \"We found that…\".",         regex=r'(?i)^\s*it (?:was|is|has been|should be|must be|can be) '
               r'(?:found|noted|observed|shown|argued|emphasized|considered|concluded)\b'),

    Rule("S12", "Formulaic citation", "low", 1.0,
         "“According to X (Year)…” 模板化引用，不展开讨论引文内容。",
         fix="Discuss what the cited work actually says instead of only naming it.",         regex=r'(?i)\baccording to [A-Z][A-Za-z\-\']+(?: (?:et al\.?|and [A-Z][A-Za-z\-\']+))? '
               r'\(?\d{4}\)?'),
]

PARAGRAPH_RULES_EN = [
    Rule("S02", "Template enumeration", "high", 2.5,
         "“Firstly… Secondly… Finally…” 当行文骨架。维基与 AIGC-Detector-Pro 均列为强标记。",
         fix="Drop the \"Firstly/Secondly/Finally\" scaffolding and let the content carry the order.",         regex=r'(?i)\b(?:firstly|first of all)\b[^.]{0,200}?\b(?:secondly|second)\b'
               r'|\b(?:on the one hand)\b[^.]{0,200}?\b(?:on the other hand)\b',
         scope="paragraph"),

    Rule("P02", "Canned conclusion", "high", 2.5,
         "段末用 “In conclusion” “Overall, this demonstrates” 重述一遍。维基历史指标 §Section summaries。",
         fix="Delete the closing restatement. If it does add a conclusion the reader could not derive, keep it but drop the \"In conclusion\" shell.",         regex=r'(?i)(?:in (?:conclusion|summary)|overall|taken together|in essence)\b'
               r'[^.!?]{0,120}[.!?]?\s*$',
         scope="paragraph"),

    Rule("P03", "Challenges-and-future template", "medium", 2.0,
         "“Despite these challenges… future research will…” 提纲式收尾。维基 WP:FACESCHALLENGES。",
         fix="Replace the template ending with something specific: which limitation, and what exactly you would do next.",         regex=r'(?i)\bdespite (?:these|its|the) (?:challenges|limitations|advances)\b'
               r'|\bfaces? (?:several|numerous|various) challenges\b'
               r'|\bfuture (?:research|work|studies) (?:will|should|could|may)\b',
         scope="paragraph"),
]
