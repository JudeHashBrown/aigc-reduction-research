"""生成不同技术路线的改写样本，看哪条能真正推动检测器分数。

朱雀实测已经否掉了「让通用助手改得不像 AI」这条路（改 59% 字数，分数不动）。
但那只否掉了一种条件分布。下面四条都是**全自动**的，产品上可行：

T1 回译：中→英→中。仍过模型，但翻译的条件分布与自由生成不同，
   受源文约束强得多，理论上会落到不一样的 token 分布里。
T2 少样本条件化：把真人写的文本当范例喂进去，让模型从「那位作者的分布」
   里采样，而不是从助手的默认分布。这是最可能成立的一条——
   R4 的失败正是因为它仍在助手的默认分布里。
T3 非神经扰动：纯代码的句子重排 + 分句重组。完全不经模型采样，
   因此不可能「重新注入 AI 统计特征」。
T4 换模型：用另一个模型做同样的激进改写，排除「只是这个模型被检测器认得熟」。

用法：
    export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...
    python3 probe/tactics.py
"""
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))

from llm import Client, LLMError      # noqa: E402

OUT = ROOT / "out" / "_tactics"
SRC = ROOT / "bases" / "b11_材料.txt"
HUMAN = ROOT.parent / "samples" / "human_sample.txt"


def t1_roundtrip(client, src):
    """中 → 英 → 中。两步都只给翻译指令，不给任何风格要求。"""
    en = client.complete(
        "You are a professional translator.",
        "Translate the following Chinese academic text into English. "
        "Output only the translation.\n\n" + src, n=1)[0].strip()
    zh = client.complete(
        "你是专业翻译。",
        "把下面的英文学术文字翻译成中文。只输出译文。\n\n" + en, n=1)[0].strip()
    return zh


def t2_fewshot(client, src, human):
    """把真人文本当范例，让模型从那位作者的分布里采样。

    R4 失败的原因很可能是：无论怎么要求「不像 AI」，模型仍在自己的
    默认助手分布里采样。给它一段真人文本当锚，是换分布而不是换措辞。
    """
    sys_p = ("你是中文学术写作者。下面给你一段真人写的学术文字作为文风范例。"
             "请完全按照这段范例的句子长短、标点习惯、用词偏好、"
             "信息密度和语气来改写用户给的文本。"
             "保持原文的全部事实、术语和结论不变，不要新增任何信息。"
             "只输出改写后的正文。\n\n"
             "【文风范例】\n" + human)
    return client.complete(sys_p, "请按范例文风改写下面这段：\n\n" + src, n=1)[0].strip()


def t3_shuffle(src):
    """纯代码扰动：段内句子重排 + 长句在逗号处拆分。

    完全不经模型，因此不可能把 AI 统计特征重新采样回来。
    代价是可读性会下降——这条主要用来回答一个问题：
    检测器到底看不看句子顺序和句长结构。
    """
    rng = random.Random(20260922)
    out = []
    for para in src.split("\n\n"):
        sents = [s for s in re.split(r'(?<=[。！？])', para) if s.strip()]
        if len(sents) >= 3:
            head, body, tail = sents[0], sents[1:-1], sents[-1]
            rng.shuffle(body)
            sents = [head] + body + [tail]
        rebuilt = []
        for s in sents:
            # 长句在中间的逗号处断成两句
            if len(s) > 45 and "，" in s:
                # rindex 在窗口里找不到会抛 ValueError，不是返回 -1
                i = s.rfind("，", 10, len(s) - 10)
                if i > 0:
                    rebuilt.append(s[:i] + "。")
                    rebuilt.append(s[i + 1:])
                    continue
            rebuilt.append(s)
        out.append("".join(rebuilt))
    return "\n\n".join(out)


def t4_other_model(src, model):
    """换一个模型做同样的激进改写，排除「只是这个模型被认得熟」。"""
    c = Client(model=model)
    return c.complete(
        "你是中文写作专家。",
        "请改写下面这段学术文字，让它读起来不像 AI 生成的，"
        "尽量降低 AI 检测率。保持原意和专业性。只输出改写后的正文。\n\n" + src,
        n=1)[0].strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = SRC.read_text(encoding="utf-8").strip()
    human = HUMAN.read_text(encoding="utf-8").strip()
    client = Client()

    jobs = [
        ("T1_回译", lambda: t1_roundtrip(client, src)),
        ("T2_少样本条件化", lambda: t2_fewshot(client, src, human)),
        ("T3_非神经扰动", lambda: t3_shuffle(src)),
    ]
    alt = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if alt:
        jobs.append((f"T4_换模型_{alt}", lambda: t4_other_model(src, alt)))

    import difflib
    for name, fn in jobs:
        try:
            text = fn()
        except LLMError as exc:
            print(f"  {name:22s} 失败：{exc}")
            continue
        (OUT / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        ch = sum(max(i2 - i1, j2 - j1)
                 for op, i1, i2, j1, j2 in
                 difflib.SequenceMatcher(None, src, text).get_opcodes() if op != "equal")
        print(f"  {name:22s} {len(text):4d} 字   改动 {ch/len(src)*100:3.0f}%")
    print(f"\n生成在 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
