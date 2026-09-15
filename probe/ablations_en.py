"""英文侧确定性消融。规则编号与中文侧对齐，便于合并分析效应量。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import lexicon_en as LEX


def _drop_terms(text, terms):
    """英文只做替换，不做删除——除非该词在 DELETABLE 白名单里。

    中文删掉一个词句子通常还通顺，英文删掉动词或分词会直接把句子弄断。
    而语法错误本身就是一种可检测的异常，比原来的 AI 味更糟。
    没有替换词又不可删的，宁可留着不动。
    """
    n = 0
    for t in sorted(terms, key=len, reverse=True):
        key = t.lower()
        sug = LEX.SUGGEST.get(key)
        pat = r'\b' + re.escape(t) + r'\b'
        if sug:
            text, k = re.subn(pat, sug, text, flags=re.I)
        elif key in LEX.DELETABLE:
            text, k = re.subn(pat + r'[,;]?\s*', '', text, flags=re.I)
        else:
            k = 0                       # 无安全改法，保持原样
        n += k
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:])', r'\1', text)
    # 删词后句首可能剩小写，补回大写
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    return text, n


def ablate_vocab_t1(text):
    return _drop_terms(text, LEX.T1)


def ablate_vocab_t2(text):
    return _drop_terms(text, LEX.T2)


def ablate_s03(text):
    """Negative parallelism → 平铺。"""
    n = 0
    text, k = re.subn(r'(?i)\bnot (?:just|only|merely|simply)\b\s*', '', text); n += k
    text, k = re.subn(r'(?i),?\s*\bbut also\b\s*', ' and ', text); n += k
    text, k = re.subn(r'(?i),?\s*\bbut\b\s+(?=\w)', ' and ', text, count=n and 1 or 0); n += k
    return text, n


def ablate_s04(text):
    """Copula avoidance → is。"""
    n = 0
    for pat, rep in [(r'(?i)\bserves as\b', 'is'), (r'(?i)\bstands as\b', 'is'),
                     (r'(?i)\bfunctions as\b', 'is'), (r'(?i)\bacts as\b', 'is'),
                     (r'(?i)\brepresents a\b', 'is a'), (r'(?i)\brefers to\b', 'is'),
                     (r'(?i)\bboasts\b', 'has')]:
        text, k = re.subn(pat, rep, text); n += k
    return text, n


def ablate_s05(text):
    """Superficial -ing tail → 整段删除。"""
    return re.subn(
        r'(?i),\s(?:highlighting|underscoring|emphasizing|showcasing|reflecting'
        r'|demonstrating|illustrating|ensuring|contributing to|fostering'
        r'|solidifying|cementing|symbolizing|marking)\b[^.;!?]{0,80}(?=[.;!?])',
        '', text)


def ablate_s07(text):
    """Vague attribution → 删除引导语。"""
    n = 0
    text, k = re.subn(
        r'(?i)\b(?:experts?|scholars?|researchers?|observers?|critics?|analysts?|'
        r'commentators?|some)\s+(?:argue|suggest|note|contend|believe|point out)\s+that\s+',
        '', text); n += k
    text, k = re.subn(
        r'(?i)\b(?:studies|research|evidence|data)\s+(?:show|shows|suggest|suggests|'
        r'indicate|indicates)\s+that\s+', '', text); n += k
    text, k = re.subn(r'(?i)\bit is (?:widely |generally )?(?:believed|accepted|acknowledged) that\s+',
                      '', text); n += k
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    return text, n


def ablate_s08(text):
    """Canned significance → 优先只摘掉套话，剩不下实质内容时才删整句。

    与中文侧同理：整句删除会连同句中真正有信息的部分一起丢掉，
    而信息丢失比 AI 味严重得多。
    """
    PHRASE = (r'(?i)(?:,\s*)?(?:which )?(?:plays? an? (?:crucial|vital|pivotal|key|significant|important) role(?: in [^,.;!?]{0,40})?'
              r'|(?:is|stands|serves) as a testament(?: to [^,.;!?]{0,40})?'
              r'|underscor(?:es|ing) the (?:importance|significance|need)(?: (?:of|for) [^,.;!?]{0,40})?'
              r'|highlights? the (?:importance|significance)(?: of [^,.;!?]{0,40})?'
              r'|paving the way(?: for [^,.;!?]{0,40})?'
              r'|opens? (?:up )?new (?:avenues|possibilities|frontiers)(?: for [^,.;!?]{0,40})?)')
    n, out = 0, []
    for sent in re.split(r'(?<=[.!?])\s+', text):
        if not sent.strip() or not re.search(PHRASE, sent):
            out.append(sent)
            continue
        trimmed = re.sub(PHRASE, '', sent)
        trimmed = re.sub(r'\s+([.,;:])', r'\1', trimmed)
        trimmed = re.sub(r',\s*\.', '.', trimmed)
        core = re.sub(r'[^A-Za-z]', '', trimmed)
        if len(core) >= 20:                      # 还有实质内容 → 保住
            out.append(trimmed)
        n += 1
    return " ".join(x for x in out if x.strip()), n


def ablate_p02(text):
    """段末 In conclusion / Overall 套句 → 删除。"""
    n = 0
    out = []
    for para in text.split('\n'):
        new, k = re.subn(
            r'(?i)[^.!?]*\b(?:in (?:conclusion|summary)|overall|taken together|in essence)\b'
            r'[^.!?]*[.!?]?\s*$', '', para)
        out.append(new); n += k
    return "\n".join(out), n


def ablate_f01(text):
    return re.subn(r'—|--(?!-)', ', ', text)


ABLATIONS_EN = {
    "V-T1": ("EN T1 vocabulary", ablate_vocab_t1),
    "V-T2": ("EN T2 vocabulary", ablate_vocab_t2),
    "S04": ("Copula avoidance", ablate_s04),
    "S05": ("Superficial -ing tail", ablate_s05),
    "S07": ("Vague attribution", ablate_s07),
    "S08": ("Canned significance", ablate_s08),
    "P02": ("Canned conclusion", ablate_p02),
    "F01": ("Em dash", ablate_f01),
}
