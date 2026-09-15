"""不变量测试。不测「功能对不对」，测「绝不能发生什么」。

七条不变量：
  I1 偏移正确   finding.matched 必须等于 text[start:end]
  I2 确定性     同一输入跑两次结果必须完全一致
  I3 不丢事实   代码层不得丢失任何数字/专名/引用
  I4 不伤人文   人写文本必须零改动
  I5 幂等       codefix(codefix(x)) == codefix(x)
  I6 无残句     修复后不得出现悬空标点、空句、重复标点
  I7 不崩       任何输入都不能抛异常
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "probe"))

import guard
from codefix import codefix
from diagnose import diagnose

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(f"{name}: {detail}")
    return cond


CASES = {
    "中文AI稿": open(ROOT / "samples/ai_sample.txt", encoding="utf-8").read(),
    "混排稿": open(ROOT / "samples/mixed_sample.txt", encoding="utf-8").read(),
    "人写稿": open(ROOT / "samples/human_sample.txt", encoding="utf-8").read(),
    "空": "",
    "空白": "   \n\n  \t ",
    "单字": "好",
    "无标点": "深入探讨系统梳理综合运用至关重要",
    "纯数字": "1 2 3 4.5 67% p<0.01",
    "纯英文AI": "This paper delves into a pivotal realm. Studies show it plays a crucial role, "
                "underscoring the importance of robust, scalable, and comprehensive methods. "
                "In conclusion, despite these challenges, future research will explore this.",
    "正则字符": "研究 f(x)=a*b+c[i] 与 g(x)={1,2}|h 的关系，具有重要意义。参见[1]、[2-3]。",
    "CRLF": "第一段，具有重要意义。\r\n\r\n第二段，研究表明如此。\r\n",
    "emoji": "本文🔬深入探讨了该问题🎯，具有重要意义。",
    "全角空格": "本文　深入探讨　了该问题，具有重要意义。",
    "长单段": "本文深入探讨了该问题，综上所述，具有重要意义。" * 60,
    "嵌套引号": '如《深度学习》所言，"效果显著"，此外，具有重要意义。',
    "中英混句": "我们用 ResNet-50 在 CIFAR-10 上训练，AUC 达 0.92，这充分说明了方法的有效性。",
    "只有套话": "综上所述。由此可见。具有重要意义。",
    "表格式": "| 指标 | 值 |\n| MAE | 21.3 |\n综上所述，具有重要意义。",
    "Markdown": "## 标题\n- **要点一**：深入探讨\n- **要点二**：系统梳理\n\n综上所述。",
    "换行密集": "一句。\n\n\n\n二句，具有重要意义。\n\n\n",
}

# ---- I7 不崩 + I1 偏移 + I2 确定性 -------------------------------------
for name, text in CASES.items():
    try:
        r1 = diagnose(text)
    except Exception as e:
        FAILS.append(f"I7 诊断崩溃 [{name}]: {type(e).__name__}: {e}")
        continue
    for f in r1["findings"]:
        seg = text[f["start"]:f["end"]]
        check("I1 偏移", seg == f["matched"],
              f"[{name}] {f['rule_id']} 期望「{f['matched']}」实得「{seg}」")
        check("I1 越界", 0 <= f["start"] <= f["end"] <= len(text),
              f"[{name}] {f['rule_id']} span=({f['start']},{f['end']}) len={len(text)}")
    try:
        r2 = diagnose(text)
        check("I2 确定性", r1 == r2, f"[{name}] 两次诊断结果不同")
    except Exception as e:
        FAILS.append(f"I7 二次诊断崩溃 [{name}]: {e}")

# ---- I3/I5/I6 代码层 ----------------------------------------------------
DANGLING = [
    (r'[，,、]\s*[。！？；]', "逗号紧跟句号"),
    (r'[。！？；]\s*[。！？；]', "重复句末标点"),
    (r'(?m)^[，,、。；：]', "段首孤立标点"),
    (r'[，,、：]\s*$', "段尾悬空逗号"),
    (r'很[的了着]', "很+虚词"),
    (r'是，', "是后紧跟逗号"),
    (r'\s{3,}', "连续空格"),
    (r'[a-z]\s+[.,;]', "英文标点前空格"),
]

for name, text in CASES.items():
    try:
        out1, _ = codefix(text)
    except Exception as e:
        FAILS.append(f"I7 修复崩溃 [{name}]: {type(e).__name__}: {e}")
        continue

    g = guard.compare(text, out1)
    check("I3 丢事实", g["n_removed"] == 0,
          f"[{name}] 丢失 {g['n_removed']} 项：{guard.describe(g)[:90]}")
    check("I3 造事实", not g["fabricated"],
          f"[{name}] {guard.describe(g)[:90]}")

    try:
        out2, _ = codefix(out1)
        check("I5 幂等", out1 == out2,
              f"[{name}] 二次修复又变了：「{out1[:45]}」→「{out2[:45]}」")
    except Exception as e:
        FAILS.append(f"I7 二次修复崩溃 [{name}]: {e}")

    for pat, why in DANGLING:
        m = re.search(pat, out1)
        check("I6 残句", not m,
              f"[{name}] {why}：…{out1[max(0,m.start()-14):m.end()+10]}…" if m else "")

# ---- I4 人写零改动 ------------------------------------------------------
hs = CASES["人写稿"]
out, _ = codefix(hs)
check("I4 人写零改动", out.strip() == hs.strip(), "人写文本被修改了")

# ---- 报告 --------------------------------------------------------------
print(f"用例 {len(CASES)} 个，不变量 7 条")
if FAILS:
    print(f"\n✗ {len(FAILS)} 项失败：\n")
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("\n✓ 全部通过")


def test_rule_coverage():
    """每条规则必须恰好归属一层：代码层、LLM 层、或明确的只报告。

    P02 曾被 CODE_HANDLED 声称由代码处理、而 SAFE_ZH 里根本没有，
    于是一条 high 级规则两层都不管，诊断报得出来却永远修不掉。
    这个断言让那种夹缝不可能再悄悄出现。
    """
    import patterns, patterns_en
    from rewrite import CODE_HANDLED, SEMANTIC, REPORT_ONLY
    from codefix import SAFE_ZH, SAFE_EN
    bad = []
    for lang, rules, safe in (("zh", patterns.ALL_RULES, SAFE_ZH),
                              ("en", patterns_en.SENTENCE_RULES_EN
                               + patterns_en.PARAGRAPH_RULES_EN, SAFE_EN)):
        ids = {r.rule_id for r in rules} | {"V-T1", "V-T2"}
        code, sem, rep = set(CODE_HANDLED[lang]), set(SEMANTIC[lang]), set(REPORT_ONLY[lang])
        for rid in sorted(ids):
            homes = [n for n, g in (("code", code), ("llm", sem), ("report", rep)) if rid in g]
            if len(homes) != 1:
                bad.append(f"{lang}/{rid}: 归属 {homes or '无'}")
        for rid in sorted(code - set(safe)):
            bad.append(f"{lang}/{rid}: CODE_HANDLED 声称代码处理，但不在 SAFE 列表里")
    assert not bad, "规则归属有问题:\n  " + "\n  ".join(bad)


def test_rules_reachable():
    """每条注册的规则都必须在 diagnose 的执行路径上。

    新规则只加进 ALL_RULES 而没并进 SENTENCE_RULES/PARAGRAPH_RULES/FORMAT_RULES 时，
    RULES_BY_ID 查得到、覆盖审计也过，但诊断永远不会命中它——
    与 P02 同一类错误：注册表不等于执行路径。
    """
    import patterns as P, patterns_en as PE
    for name, mod, lists in (
            ("zh", P, (P.SENTENCE_RULES, P.PARAGRAPH_RULES, P.FORMAT_RULES)),
            ("en", PE, (PE.SENTENCE_RULES_EN, PE.PARAGRAPH_RULES_EN))):
        executed = {r.rule_id for lst in lists for r in lst}
        registered = ({r.rule_id for r in mod.ALL_RULES} if name == "zh"
                      else {r.rule_id for lst in lists for r in lst})
        missing = sorted(registered - executed)
        assert not missing, f"{name}: 这些规则注册了但诊断跑不到: {missing}"
