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
    out = []
    pat = r'\b(\w+(?:\s\w+){0,2}),\s(\w+(?:\s\w+){0,2}),\s+and\s(\w+(?:\s\w+){0,2})\b'
    for m in re.finditer(pat, text):
        g = m.groups()
        tail = [len(x.split()) for x in g[1:]]
        if max(tail) - min(tail) > 1:
            continue
        if len(g[0].split()) < min(tail):
            continue
        out.append((m.start(), m.end(), m.group(0)))
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
    Rule("S01", "Rule of three", "high", 2.5,
         "三项等长并列（“fast, reliable, and scalable”）。维基 WP:RO3 列为 AI 强标记。",
         finder=find_rule_of_three),

    Rule("S03", "Negative parallelism", "high", 3.0,
         "“not just X, but Y” / “It's not X, it's Y”。维基 WP:AIPARALLEL，最典型的 AI 句式。",
         regex=r'(?i)\bnot (?:just|only|merely|simply)\b[^.;!?]{2,60}?\bbut\b[^.;!?]{2,60}'
               r'|\bit(?:\'s| is| was) not\b[^.;!?]{2,50}?,?\s*(?:it(?:\'s| is)|but)\b[^.;!?]{2,50}'
               r'|\brather than\b[^.;!?]{2,50}'),

    Rule("S04", "Copula avoidance", "medium", 2.0,
         "用 serves as / stands as / represents 回避 is。维基 WP:AINOCOPULA。",
         regex=r'(?i)\b(?:serves?|serving|stands?|functions?|operates?|acts?) as\b'
               r'|\brepresents? an?\b|\bboasts?\b|\brefers to\b'),

    Rule("S05", "Superficial -ing tail", "high", 2.5,
         "句尾挂 -ing 分词短语制造深刻感（维基 WP:SUPERFICIAL），不带新信息。",
         regex=r'(?i),\s(?:highlighting|underscoring|emphasizing|showcasing|reflecting'
               r'|demonstrating|illustrating|ensuring|contributing to|fostering'
               r'|solidifying|cementing|symbolizing|marking)\b[^.;!?]{0,60}'),

    Rule("S07", "Vague attribution", "high", 3.0,
         "“experts argue” “studies show” 却不给出处。维基 WP:AIWEASEL。",
         regex=r'(?i)\b(?:experts?|scholars?|researchers?|observers?|critics?|analysts?|'
               r'commentators?|industry reports?|some)\s+'
               r'(?:argue|suggest|note|contend|have (?:cited|noted|argued)|believe|point out)\b'
               r'|\b(?:studies|research|evidence|data)\s+(?:show|shows|suggest|suggests|indicate|indicates)\b'
               r'|\bit is (?:widely |generally )?(?:believed|accepted|acknowledged)\b'),

    Rule("S08", "Canned significance", "high", 3.0,
         "“plays a crucial role” “is a testament to” “underscores the importance”。维基 WP:AILEGACY。",
         regex=r'(?i)\bplays? an? (?:crucial|vital|pivotal|key|significant|important) role\b'
               r'|\b(?:is|stands|serves) as a testament\b'
               r'|\bunderscor(?:es|ing) the (?:importance|significance|need)\b'
               r'|\bhighlights? the (?:importance|significance)\b'
               r'|\bmark(?:s|ing) a (?:pivotal|significant|key) (?:moment|shift|turning point)\b'
               r'|\bpaving the way\b|\bopens? (?:up )?new (?:avenues|possibilities|frontiers)\b'),

    Rule("S09", "Hedging stack", "medium", 1.5,
         "一句里堆两个以上对冲表达。AIGC-Detector-Pro：hedging 密度 >6% 可疑。",
         finder=find_hedge_stack_en),

    Rule("S11", "Passive opener", "medium", 1.5,
         "“It was found that…” “It should be noted that…” 这类无主体被动开头。",
         regex=r'(?i)^\s*it (?:was|is|has been|should be|must be|can be) '
               r'(?:found|noted|observed|shown|argued|emphasized|considered|concluded)\b'),

    Rule("S12", "Formulaic citation", "low", 1.0,
         "“According to X (Year)…” 模板化引用，不展开讨论引文内容。",
         regex=r'(?i)\baccording to [A-Z][A-Za-z\-\']+(?: (?:et al\.?|and [A-Z][A-Za-z\-\']+))? '
               r'\(?\d{4}\)?'),
]

PARAGRAPH_RULES_EN = [
    Rule("S02", "Template enumeration", "high", 2.5,
         "“Firstly… Secondly… Finally…” 当行文骨架。维基与 AIGC-Detector-Pro 均列为强标记。",
         regex=r'(?i)\b(?:firstly|first of all)\b[^.]{0,200}?\b(?:secondly|second)\b'
               r'|\b(?:on the one hand)\b[^.]{0,200}?\b(?:on the other hand)\b',
         scope="paragraph"),

    Rule("P02", "Canned conclusion", "high", 2.5,
         "段末用 “In conclusion” “Overall, this demonstrates” 重述一遍。维基历史指标 §Section summaries。",
         regex=r'(?i)(?:in (?:conclusion|summary)|overall|taken together|in essence)\b'
               r'[^.!?]{0,120}[.!?]?\s*$',
         scope="paragraph"),

    Rule("P03", "Challenges-and-future template", "medium", 2.0,
         "“Despite these challenges… future research will…” 提纲式收尾。维基 WP:FACESCHALLENGES。",
         regex=r'(?i)\bdespite (?:these|its|the) (?:challenges|limitations|advances)\b'
               r'|\bfaces? (?:several|numerous|various) challenges\b'
               r'|\bfuture (?:research|work|studies) (?:will|should|could|may)\b',
         scope="paragraph"),
]
