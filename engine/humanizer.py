"""humanizer-zh-academic 模式：整篇改写。

为什么单开一条路径而不是塞进现有流水线：
那份 Skill 的 SOP 是**整篇级**的——「全文节奏检查」要看相邻三段是否雷同，
硬约束里「正文加粗 ≤5 处」「段末套句全文 ≤1 处」「理论起笔 ≤20% 段落」
都是全文计数，「噪声预算每千字 2-3 处」也是全文比例。
逐段喂给模型，这些约束一条都核查不了。

两种模式，差别只有一条：
  safe=True （默认）—— 保留事实守卫。跳过 Skill 里一切需要凭空添加内容的做法。
  safe=False        —— 完整执行，包括「注入学者个性」（承认局限/表达意外/留下判断）。
                       那一节会加入原文没有的主观表述和研究过程，本质是编造。
                       仅供实验，不可用于用户的真实论文。
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

import guard
from diagnose import diagnose, split_paragraphs
from llm import Client, LLMError

SKILL = (Path(__file__).resolve().parent / "prompts" / "humanizer_zh.md")

# 单次调用的文本上限。超过就按段落分块——块与块之间的全文约束只能近似，
# 这是分块的固有代价，输出里会标出来，不假装做到了。
CHUNK_CHARS = 6000

_NO_ADD = """

——————————————————————————————
【以下限制优先级高于上面任何规定】
绝对不许新增原文没有的信息：不许加数字、事实、文献、研究过程，
也不许加「出乎意料的是」「笔者认为」这类原文没有的主观判断。
因此上面「注入学者个性」一节中凡需凭空添加内容的做法一律跳过，
只执行纯改写既有文字的部分（移位、砍尾、破对称、换词、去模糊、调节奏）。
改写后的每个实词都要能在原文里指出出处。
——————————————————————————————"""

_USER = """请按上述指令改写下面的文本。文体按「期刊论文」标定。

用户已确认直接改写，跳过风险识别报告那一步，直接输出改写后的正文。
只输出正文本身，不要任何说明、标题、markdown 标记或前后言。

待改写文本：
<<<TEXT>>>
{t}
<<<END>>>"""


def _chunks(text: str) -> List[str]:
    paras = [p.text for p in split_paragraphs(text)]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > CHUNK_CHARS:
            out.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        out.append(cur)
    return out or [text]


def _clean(raw: str) -> str:
    t = re.sub(r'^```[a-zA-Z]*\n?|\n?```$', '', raw.strip())
    t = re.sub(r'^<<<TEXT>>>\s*|\s*<<<END>>>$', '', t.strip())
    return t.strip()


def humanize(text: str, client: Client, safe: bool = True,
             progress=None) -> Dict:
    """整篇改写。返回结果与逐块记录。"""
    sys_prompt = SKILL.read_text(encoding="utf-8")
    if safe:
        sys_prompt += _NO_ADD

    before = diagnose(text)
    parts = _chunks(text)
    outs, errs = [], []
    for i, part in enumerate(parts):
        try:
            cand = _clean(client.complete(sys_prompt, _USER.format(t=part), n=1)[0])
        except LLMError as exc:
            errs.append(f"第 {i+1} 块调用失败：{exc}")
            cand = part
        if not cand or len(cand) < len(part) * 0.4:
            errs.append(f"第 {i+1} 块输出异常（{len(cand)} 字 vs 原 {len(part)} 字），保留原文")
            cand = part
        outs.append(cand)
        if progress:
            progress(i + 1, len(parts))

    out = "\n\n".join(outs)
    after = diagnose(out)
    g = guard.compare(text, out)

    notes = list(errs)
    if len(parts) > 1:
        notes.append(
            f"文本分成了 {len(parts)} 块。该 Skill 的「全文节奏检查」和"
            f"「正文加粗 ≤5 处」等全文级约束只能在块内近似满足，跨块无法保证。")
    if not safe:
        notes.append(
            "本次关闭了编造守卫，完整执行了「注入学者个性」。"
            "输出中可能含有原文没有的主观表述与研究过程描述——"
            "这在真实论文里是学术不端，仅供实验。")

    return {
        "text": out,
        "mode": "humanizer" if not safe else "humanizer-safe",
        "before": before["summary"],
        "after": after["summary"],
        "after_full": after,
        "n_chunks": len(parts),
        "guard": {
            "fabricated": g["fabricated"],
            "added": g["added"],
            "terms_lost": g["terms_lost"],
            "n_removed": g["n_removed"],
        },
        "notes": notes,
    }
