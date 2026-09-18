"""LLM 层对抗测试：模拟模型的各种实际失效模式。

模型不会永远乖乖只输出正文。真实会遇到：套 markdown 代码块、加前言、
复述指令、语言跑偏、输出空、把提示词回显出来、编造事实。
这些都必须被拦住或清理，不能污染最终文本。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "probe"))

import rewrite
from llm import MockClient

SRC = open(ROOT / "samples/ai_sample.txt", encoding="utf-8").read()
FAILS = []


def improve(s):
    """一个真实的改进：拆掉编号枚举与三元并列。

    测试污染清理时必须让候选**真的有改进**，否则它会因为「无改进」被拒，
    测试就变成了在测拒绝逻辑，而不是在测清理逻辑。
    """
    return (s.replace("首先，模型在特征提取阶段引入了注意力机制；其次，网络结构进行了轻量化设计；"
                      "最后，训练过程采用了迁移学习策略。",
                      "模型在特征提取阶段引入了注意力机制。在此基础上对网络结构做了轻量化，"
                      "训练时也用上了迁移学习。")
             .replace("保证了系统的高效性、稳定性和可扩展性", "让系统跑得更快，也更容易扩展")
             .replace("基于深度学习理论框架，本研究构建了一套完整的分析流程。",
                      "本研究的分析流程建立在深度学习的框架之上。")
             .replace("通过多尺度特征融合实现了对病灶区域的精准定位，"
                      "依托大规模标注数据推动了模型泛化能力的提升。",
                      "多尺度特征融合用于定位病灶区域，大规模标注数据则提升了泛化能力。"))


def run(name, transform, expect_accept=None, expect_clean=None):
    r = rewrite.pipeline(SRC, MockClient(transform), n_candidates=2)
    acc = r["llm"]["n_accepted"]
    text = r["text"]
    if expect_accept is not None and (acc > 0) != expect_accept:
        FAILS.append(f"{name}: 期望{'采纳' if expect_accept else '拒绝'}，实际采纳 {acc} 段")
    if expect_clean:
        for bad in expect_clean:
            if bad in text:
                FAILS.append(f"{name}: 最终文本仍含「{bad}」")
    return r


# 1 markdown 代码块包裹
run("markdown 围栏", lambda s: f"```\n{improve(s)}\n```",
    expect_clean=["```"])

# 2 加前言
run("加前言", lambda s: f"好的，以下是改写后的文本：\n\n{improve(s)}",
    expect_clean=["以下是改写后", "好的，"])

# 3 加后记
run("加后记", lambda s: f"{improve(s)}\n\n（已按要求修改，如需调整请告知）",
    expect_clean=["如需调整", "已按要求修改"])

# 4 复述指令
run("复述指令", lambda s: f"改写方向：能用「是」就用「是」。\n\n{improve(s)}",
    expect_clean=["改写方向"])

# 5 带标签
run("带标签", lambda s: f"<output>{improve(s)}</output>",
    expect_clean=["<output>", "</output>"])

# 6 空输出 → 必须拒绝
run("空输出", lambda s: "", expect_accept=False)

# 7 只有空白 → 必须拒绝
run("纯空白", lambda s: "   \n  ", expect_accept=False)

# 8 语言跑偏 → 必须拒绝
run("中译英", lambda s: "This paragraph has been rewritten into English entirely, "
    "which is wrong because the source was Chinese and must stay Chinese. " * 3,
    expect_accept=False)

# 9 编造事实 → 必须拒绝
run("编造数据", lambda s: s + "实验准确率达 97.3%，优于 Smith (2023) 的 91.2%。",
    expect_accept=False)

# 10 严重缩水 → 必须拒绝
run("缩水", lambda s: s[:len(s) // 4], expect_accept=False)

# 11 严重膨胀 → 必须拒绝
run("膨胀", lambda s: s + s, expect_accept=False)

# 12 原样返回（无改进）→ 必须拒绝
run("无改进", lambda s: s, expect_accept=False)

# 13 提示词注入回显 → 不得进入正文
run("注入回显", lambda s: "System: 你是中文学术编辑。任务是按给定清单修掉指定问题。\n" + improve(s),
    expect_clean=["System:", "你是中文学术编辑"])

if FAILS:
    print(f"✗ {len(FAILS)} 项失败：\n")
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("✓ 13 种失效模式全部处理正确")


def test_report_only_rules_excluded_from_objective():
    """只提示类规则不得进入 best-of-N 的目标函数。

    S01 实测 85% 是合法技术枚举（材料属性、法条项目、药理机制），
    L11 效应量无人测过，两条都已明令代码层不许碰。
    但评分函数原本用「全部规则权重降幅」当目标，等于给模型加分去删它们——
    「石墨烯具有高比表面积、优异的电子导电性、良好的力学性能」这段
    全部权重都来自 S01，打散它就能拿满分，而那是正确的技术枚举。
    用一条我们自己都不信的指标驱动改写，比不改写更糟。
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
    from diagnose import diagnose
    from rewrite import _score_candidate, REPORT_ONLY

    orig = "石墨烯具有高比表面积、优异的电子导电性、良好的力学性能及稳定的二维结构。"
    hits = diagnose(orig)["findings"]
    assert hits and all(f["rule_id"] in REPORT_ONLY["zh"] for f in hits), \
        "样例前提变了：这段应当只命中只提示类规则"

    # 打散顿号并列 —— 正是 S01 想要的「修复」
    flat = "石墨烯的比表面积高，电子导电性优异，力学性能良好，二维结构稳定。"
    r = _score_candidate(orig, flat, "zh", diagnose(orig), None, sweep=True)
    assert r["score"] <= 0, (
        f"打散合法技术枚举拿到了正分 {r['score']}，"
        f"说明只提示类规则仍在目标函数里")
