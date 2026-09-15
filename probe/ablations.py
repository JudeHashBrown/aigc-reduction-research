"""单特征消融：用确定性代码移除某一种 AI 特征，其余保持不变。

为什么必须用代码而不是 LLM：
LLM 改写会同时改动句长、用词、语序、结构等多个变量，测出来的分数变化
无法归因到任何单一特征。五个参考项目都不知道自己哪条规则真正有用，
根源就在这里。确定性消融才能做因果归因。

每个函数签名：ablate(text) -> (new_text, n_changes)
改不动就原样返回，n_changes=0。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import lexicon as LEX


def tidy_zh(text: str) -> str:
    """删改之后的标点收尾。

    删掉一个短语常会留下孤立标点（「可解释性，。」）或重复标点。
    这些残留本身就是明显的机器痕迹，必须清干净。
    """
    text = re.sub(r'[，,、]\s*([。！？；])', r'\1', text)      # 「，。」→「。」
    text = re.sub(r'([，,、])\s*[，,、]+', r'\1', text)         # 重复逗号顿号
    text = re.sub(r'([。！？；])\s*[。！？；]+', r'\1', text)     # 重复句号
    text = re.sub(r'(?m)^[，,、。；：]+\s*', '', text)          # 段首孤立标点
    text = re.sub(r'[，,、：]\s*$', '。', text.rstrip())        # 段尾悬空逗号
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _sub_count(pattern, repl, text, flags=0):
    new, n = re.subn(pattern, repl, text, flags=flags)
    return new, n


# ---------- 词表类 --------------------------------------------------------

def ablate_vocab_t1(text):
    """移除 T1 强标记词：有替换建议的替换，没有的删除。"""
    n = 0
    for term in sorted(LEX.T1, key=len, reverse=True):
        if term not in text:
            continue
        sug = LEX.SUGGEST.get(term)
        if sug:
            text, k = _sub_count(re.escape(term), sug, text)
        elif term in LEX.DELETABLE:
            text, k = _sub_count(re.escape(term) + r'[，,]?', "", text)
        else:
            k = 0                      # 无安全改法，保持原样
        n += k
    text = re.sub(r'[，,]\s*[，,]', '，', text)
    text = re.sub(r'^[，,。、]+', '', text, flags=re.M)
    return text, n


def ablate_vocab_t2(text):
    n = 0
    for term in sorted(LEX.T2, key=len, reverse=True):
        if term not in text:
            continue
        sug = LEX.SUGGEST.get(term)
        if sug:
            text, k = _sub_count(re.escape(term), sug, text)
        elif term in LEX.DELETABLE:
            text, k = _sub_count(re.escape(term) + r'[，,]?', "", text)
        else:
            k = 0                      # 无安全改法，保持原样
        n += k
    text = re.sub(r'[，,]\s*[，,]', '，', text)
    return text, n


# ---------- 句式类 --------------------------------------------------------

def ablate_s01_triple(text):
    """整齐三元并列 → 保留两项。「A、B和C」→「A和B」"""
    def repl(m):
        items = [i for i in re.split(r'、|和|以及|与', m.group(0)) if i]
        return items[0] + "和" + items[1] if len(items) >= 2 else m.group(0)
    pat = r'[^，。；：！？、\s]{2,12}(?:、[^，。；：！？、\s]{2,12}){1,}(?:(?:和|以及|与)[^，。；：！？、\s]{2,12})?'
    n = 0
    out = []
    last = 0
    for m in re.finditer(pat, text):
        items = [i for i in re.split(r'、|和|以及|与', m.group(0)) if i]
        if len(items) < 3:
            continue
        tail = [len(i) for i in items[1:]]
        if max(tail) - min(tail) > 2:
            continue
        out.append(text[last:m.start()]); out.append(repl(m)); last = m.end(); n += 1
    out.append(text[last:])
    return "".join(out), n


def ablate_s02_enum(text):
    """编号枚举骨架 → 去掉序号标记，保留内容。"""
    n = 0
    for pat in [r'首先[，,]\s*', r'其次[，,]\s*', r'最后[，,]\s*', r'再次[，,]\s*',
                r'一是', r'二是', r'三是', r'第一[，,]\s*', r'第二[，,]\s*', r'第三[，,]\s*']:
        text, k = _sub_count(pat, '', text)
        n += k
    text, k = _sub_count(r'一方面[，,]?\s*', '', text); n += k
    text, k = _sub_count(r'另一方面[，,]?\s*', '同时', text); n += k
    return text, n


def ablate_s03_neg_parallel(text):
    """否定式排比 →平铺并列。「不仅A，更是B」→「A，也B」"""
    n = 0
    text, k = _sub_count(r'不仅(?:仅)?', '', text); n += k
    text, k = _sub_count(r'(?<![不])更是', '也', text); n += k
    text, k = _sub_count(r'不(?:只|止)是', '', text); n += k
    text, k = _sub_count(r'并非(.{2,30}?)而是', r'\1不是，实际是', text); n += k
    return text, n


def ablate_s04_copula(text):
    """回避系动词 → 还原成「是」。

    仅供探测实验使用，**不用于生产修复**：「很X」只在 X 是形容词时成立，
    遇到动词短语会产出「很承上启下」这种病句。生产路径由 LLM 层处理。
    """
    n = 0
    # 捕获必须用惰性量词：贪婪会把「的」吞进捕获组，
    # 「发挥着不可替代的作用」→「很不可替代的」，多出一个悬空的「的」。
    text, k = _sub_count(r'作为([^，。；]{2,20}?)的(?:重要)?(?:载体|组成部分|体现|基础|支撑|保障)[，,]?',
                         r'是\1，', text); n += k
    text, k = _sub_count(r'扮演(?:着)?([^，。；]{2,20}?)的?角色', r'是\1', text); n += k
    text, k = _sub_count(r'充当(?:着)?([^，。；]{2,20}?)的?(?:角色|功能|作用)', r'是\1', text); n += k
    text, k = _sub_count(r'发挥(?:着)?([^，。；]{2,20}?)的?(?:作用|功能|价值)', r'很\1', text); n += k
    text, k = _sub_count(r'起到了([^，。；]{2,20}?)的?作用', r'很\1', text); n += k
    return text, n


def ablate_s05_tail_analysis(text):
    """句尾浮泛分析 → 整段删除该从句。"""
    return _sub_count(
        r'[，,](?:从而|进而|由此|以此)?(?:凸显|彰显|体现|印证|反映|强调|说明|展现|折射)(?:了|出)[^。！？]{0,30}(?=[。！？])',
        '', text)


def ablate_s06_hollow(text):
    """空心分析句式 →去掉「通过…」「依托…」外壳，保留实际动作。"""
    n = 0
    text, k = _sub_count(r'通过([^，。；]{2,30})(?:实现|达成|完成)了?', r'用\1', text); n += k
    text, k = _sub_count(r'依托([^，。；]{2,30})推动了?', r'靠\1提升', text); n += k
    text, k = _sub_count(r'围绕([^，。；]{2,30})(?:展开|进行)', r'针对\1', text); n += k
    return text, n


def ablate_s07_vague_attr(text):
    """模糊归因 → 删除该引导语。"""
    n = 0
    text, k = _sub_count(
        r'(?:相关)?(?:专家|学者|研究者|业内人士|相关人士|有关人士|有人|不少人)(?:认为|指出|表示|强调|建议)[，,]?',
        '', text); n += k
    text, k = _sub_count(r'(?:研究|数据|实践|调查)(?:表明|显示|证明|指出)[，,]?', '', text); n += k
    text, k = _sub_count(r'(?:业内|学界)(?:普遍)?(?:认为)[，,]?', '', text); n += k
    return text, n


def ablate_s08_generic_end(text):
    """泛化结尾 → 优先只删套话本身；剩不下实质内容时才删整句。

    「未来工作将探索模型的可解释性，前景广阔。」
      只删「，前景广阔」，保住前半句的实际内容。
    「本研究具有重要的理论意义和实践价值。」
      整句都是空话，删掉。
    """
    PHRASE = (r'具有(?:重要|重大|深远|积极)的?[^，。；]{0,8}(?:意义|价值|作用|影响)'
              r'|前景(?:广阔|可期|值得期待)'
              r'|(?:为[^，。；]{0,12})?(?:提供|给出)了?(?:重要|有益|宝贵|有力)的?'
              r'(?:参考|借鉴|启示|支撑)(?:价值|意义|作用|依据)?'
              r'|(?:指明|明确)了(?:方向|路径)')
    n, out = 0, []
    for sent in re.split(r'(?<=[。！？])', text):
        if not sent.strip():
            out.append(sent)
            continue
        if not re.search(PHRASE, sent):
            out.append(sent)
            continue
        # 先只摘掉套话短语连同其前面的连接符
        trimmed = re.sub(r'[，,、]?\s*(?:' + PHRASE + r')', '', sent)
        # 删完可能留下残缺的尾分句（「…有效性，为后续研究。」），一并清掉
        trimmed = re.sub(r'[，,、]\s*[^，。；！？]{0,6}(?=[。！？]|$)', '', trimmed)
        core = re.sub(r'[，。；！？、\s]', '', trimmed)
        if len(core) >= 8:                       # 剩下的还有实质内容 → 保住
            out.append(trimmed)
        # 否则整句都是空话，丢弃
        n += 1
    return "".join(out), n


def ablate_s09_hedge(text):
    """对冲词叠加 → 每句最多保留一个。"""
    hedges = ['似乎', '或许', '大概', '在一定程度上', '某种程度上', '潜在地', '相对而言']
    n = 0
    out = []
    for sent in re.split(r'(?<=[。！？；])', text):
        kept = False
        for h in hedges:
            while h in sent:
                if not kept:
                    kept = True
                    break
                sent = sent.replace(h, '', 1)
                n += 1
        out.append(sent)
    return "".join(out), n


def ablate_p01_theory_open(text):
    """理论起笔 → 删除段首的「基于XX理论」。"""
    return _sub_count(r'(?m)^(?:依据|基于|根据|按照)[^，。；]{2,25}(?:理论|框架|模型|视角|范式|观点)[，,]?\s*',
                      '', text)


def ablate_p02_tail_summary(text):
    """段末总结套句 → 删除该句。"""
    n = 0
    out = []
    for para in text.split('\n'):
        new, k = _sub_count(
            r'[^。！？]*(?:由此可见|综上所述|综上|总的来说|总而言之|不难看出|不难发现)[^。！？]*[。！？]?\s*$',
            '', para)
        new2, k2 = _sub_count(
            r'[^。！？]*(?:这|该|此)(?:一)?(?:案例|现象|结果|发现|数据)[^。！？]{0,10}(?:印证|表明|说明|揭示|反映)了[^。！？]*[。！？]?\s*$',
            '', new)
        out.append(new2); n += k + k2
    return "\n".join(out), n


# ---------- 格式类 --------------------------------------------------------

def ablate_f01_emdash(text):
    return _sub_count(r'——|--(?!-)', '，', text)


def ablate_f02_bold(text):
    return _sub_count(r'\*\*([^*\n]{1,40})\*\*', r'\1', text)


# ---------- 统计类：句长节奏 ---------------------------------------------

def ablate_burstiness_flatten(text):
    """把句长拉平（降低变异系数）——反向消融。

    用于检验「突发性」这条三份资料都强调、但从无人验证的指标：
    如果拉平句长后分数不升，说明中文检测器根本不看这个。
    做法：拆长句（在逗号处断开），合并过短句。
    """
    n = 0
    out_paras = []
    for para in text.split('\n'):
        if not para.strip():
            out_paras.append(para); continue
        sents = [s for s in re.split(r'(?<=[。！？])', para) if s.strip()]
        rebuilt = []
        for s in sents:
            if len(s) > 45 and '，' in s:
                idx = s.rfind('，', 0, len(s) // 2 + 10)
                if idx > 12:
                    rebuilt.append(s[:idx] + '。'); rebuilt.append(s[idx + 1:]); n += 1
                    continue
            rebuilt.append(s)
        merged, buf = [], ''
        for s in rebuilt:
            if len(s) < 18:
                buf += s.rstrip('。！？') + '，'
                n += 1
            else:
                if buf:
                    merged.append(buf.rstrip('，') + '。'); buf = ''
                merged.append(s)
        if buf:
            merged.append(buf.rstrip('，') + '。')
        out_paras.append(''.join(merged))
    return "\n".join(out_paras), n


ABLATIONS = {
    "V-T1": ("T1 强标记词", ablate_vocab_t1),
    "V-T2": ("T2 中等标记词", ablate_vocab_t2),
    "S01": ("整齐三元并列", ablate_s01_triple),
    "S02": ("编号枚举骨架", ablate_s02_enum),
    "S03": ("否定式排比", ablate_s03_neg_parallel),
    "S04": ("回避系动词", ablate_s04_copula),
    "S05": ("句尾浮泛分析", ablate_s05_tail_analysis),
    "S06": ("空心分析句式", ablate_s06_hollow),
    "S07": ("模糊归因", ablate_s07_vague_attr),
    "S08": ("泛化结尾", ablate_s08_generic_end),
    "S09": ("对冲词叠加", ablate_s09_hedge),
    "P01": ("理论起笔", ablate_p01_theory_open),
    "P02": ("段末总结套句", ablate_p02_tail_summary),
    "F01": ("破折号", ablate_f01_emdash),
    "F02": ("正文加粗", ablate_f02_bold),
    "BURST": ("句长拉平(反向)", ablate_burstiness_flatten),
}
