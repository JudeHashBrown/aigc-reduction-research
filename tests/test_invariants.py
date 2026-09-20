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


def test_guard_catches_term_loss():
    """事实守卫必须看得见小写技术术语的丢失。

    旧版只认数字、专名形态的拉丁词、引用，下面四个用例全部放行（丢失 0 项），
    而 S05/S08 的改法恰恰是删句尾从句——技术贡献常常写在那儿。
    守卫放行 → 评分函数的 facts_lost 也是 0 → 这类候选反而因为
    「规则命中最少」被优先选中。
    """
    import guard
    must_catch = [
        ("en", "Our approach is efficient, underscoring the importance of "
               "spatial-temporal modeling.", "Our approach is efficient."),
        ("zh", "本文采用时空建模方法，充分说明了其有效性。", "本文采用方法。"),
        ("zh", "我们用注意力机制建模长程依赖，效果显著。", "我们建模，效果显著。"),
        ("zh", "模型在梯度下降中收敛，具有重要意义。", "模型收敛。"),
    ]
    for lang, a, b in must_catch:
        lost = guard.compare(a, b, lang)["terms_lost"]
        assert lost, f"未抓到术语丢失：{a!r} -> {b!r}"

    # 反向：合法改写不能误报，否则会把所有候选判废（英文侧曾经栽在这里）
    must_pass = [
        ("zh", "本文深入探讨了该问题，具有重要参考价值。", "本文分析了该问题。"),
        ("zh", "该技术发挥着不可替代的作用。", "该技术是关键。"),
        ("en", "This paper delves into the problem, showcasing robust results.",
               "This paper looks at the problem."),
    ]
    for lang, a, b in must_pass:
        lost = guard.compare(a, b, lang)["terms_lost"]
        assert not lost, f"误报术语丢失：{a!r} -> {b!r} 报了 {lost}"


def test_codefix_never_loses_terms():
    """代码层修完之后，不允许有任何实义术语在全文彻底消失。"""
    import glob
    import guard
    from codefix import codefix
    from diagnose import detect_lang
    bad = []
    for f in sorted(glob.glob("samples/*.txt")) + sorted(glob.glob("probe/bases/*.txt")):
        src = open(f, encoding="utf-8").read()
        out, _ = codefix(src)
        langs = ["zh", "en"] if "mixed" in f else [detect_lang(src)]
        for lang in langs:
            lost = guard.compare(src, out, lang)["terms_lost"]
            if lost:
                bad.append(f"{f} [{lang}]: {lost}")
    assert not bad, "代码层丢了术语:\n  " + "\n  ".join(bad)


def test_probe_bases_disjoint_from_dev():
    """探针基准必须与开发集（samples/）严格分离。

    probe/bases/b01_医学影像.txt 曾与 samples/ai_sample.txt 是同一个文件
    （MD5 都是 81cd0686…）。引擎是照着那篇调出来的，再拿它测效应量
    等于自测自考——校准结果一定虚高，且虚高多少无法估计。
    """
    import glob
    import hashlib
    dev = {}
    for f in glob.glob("samples/*.txt"):
        dev[hashlib.md5(open(f, "rb").read()).hexdigest()] = f
    dev_text = {open(f, encoding="utf-8").read().strip() for f in glob.glob("samples/*.txt")}
    bad = []
    for f in glob.glob("probe/bases/*.txt"):
        raw = open(f, "rb").read()
        h = hashlib.md5(raw).hexdigest()
        if h in dev:
            bad.append(f"{f} 与 {dev[h]} 完全相同")
        elif raw.decode("utf-8").strip() in dev_text:
            bad.append(f"{f} 内容与某个开发样本相同")
    assert not bad, "探针基准污染了开发集:\n  " + "\n  ".join(bad)


def test_ablation_matches_its_rule():
    """每个消融函数必须真的降低它宣称的目标规则。

    S02 重定义为「序数词当小标题」之后，ablate_s02_enum 还在删正文的
    「首先，／其次，」——文本被改动了，目标规则的命中数却一处没降，
    纯度恒为 0。这类漂移在探针里只会显示成「纯度低」，很容易被当成
    正则写宽了而放过，实际是消融和规则指的根本不是一回事。

    每条规则给一个必然命中的最小样例，消融后该规则的命中数必须下降。
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe"))
    from ablations import ABLATIONS
    from diagnose import diagnose

    SAMPLES = {
        "S01": "系统具备高可靠性、强扩展性和好维护性。",
        "S02": "一、研究背景\n\n正文。\n\n二、研究方法\n\n正文。\n\n三、研究结论\n\n正文。",
        "S03": "这不仅是技术问题，更是管理问题。",
        "S05": "该方法提升了效率，体现了其应用价值。",
        "S07": "研究表明，该方法可以降低成本。",
        "S08": "本研究具有重要的理论意义与应用价值。",
        "S09": "该方法似乎在一定程度上可能有效。",
        "P02": "前面讲了方法。综上所述，本方法有效。",
        "F01": "这是一个结论——非常重要。",
        "F02": "这是**加粗**的正文。",
        "F04": '他提到了 "数字鸿沟" 这个说法。',
        "L01": "一句话总结：这个方案成本太高。",
        "L05": "当所有人都能用工具时，效率就不再是优势。",
        "L07": "然而，该方案并不适用于所有场景。",
        "L09": "说白了，这个项目预算不足。",
        "L11": "方案有优点。然而，它并不适用于所有场景。",
        "S04": "该技术在诊断中发挥着重要的作用。",
        "S06": "通过多模态特征融合实现了跨域检索的性能提升。",
        "P01": "基于社会资本理论，本文构建了分析框架。",
        "L10": "首段内容在这里。\n\n听起来像一个普通的优化，其实不是。",
        "V-T1": "该技术发挥着不可替代的作用。",
        "V-T2": "本文深入探讨了该问题。",
    }
    # 最小样例只能证明「两边都能触发」，证明不了在真实文本上范围一致。
    # 消融比规则宽是反复出现的 bug（S02 / S09 / S01 / P02 都栽过），
    # 表现为探针里纯度恒为 0，很容易被当成正则写宽了而放过。
    # 所以再用真实基准复核一遍：消融改了文本，目标规则就必须下降。
    import glob as _glob
    bad = []
    for f in sorted(_glob.glob("probe/bases/*.txt")):
        src = open(f, encoding="utf-8").read()
        before_all = diagnose(src)["findings"]
        for rid, (name, fn) in sorted(ABLATIONS.items()):
            if rid == "BURST":
                continue
            b = sum(1 for x in before_all if x["rule_id"] == rid)
            out, n = fn(src)
            if n == 0:
                continue
            a = sum(1 for x in diagnose(out)["findings"] if x["rule_id"] == rid)
            if a >= b:
                bad.append(f"{f.split('/')[-1]} / {rid}: 消融改了 {n} 处，"
                           f"但规则命中 {b}→{a} 没下降（消融比规则宽）")
    assert not bad, "消融范围超出规则:\n  " + "\n  ".join(bad)

    bad = []
    for rid, (name, fn) in sorted(ABLATIONS.items()):
        if rid in ("BURST",):          # 反向对照，不针对单条规则
            continue
        src = SAMPLES.get(rid)
        if src is None:
            bad.append(f"{rid}（{name}）: 没有测试样例，无法验证消融与规则是否对得上")
            continue
        before = sum(1 for f in diagnose(src)["findings"] if f["rule_id"] == rid)
        assert before > 0, f"{rid}: 样例本身没命中该规则，样例写错了：{src!r}"
        out, n = fn(src)
        after = sum(1 for f in diagnose(out)["findings"] if f["rule_id"] == rid)
        if after >= before:
            bad.append(f"{rid}（{name}）: 消融后命中 {before}→{after}，没下降。"
                       f"消融改的东西和规则测的东西对不上。")
    assert not bad, "消融与规则不匹配:\n  " + "\n  ".join(bad)


def test_every_finding_has_reason_and_fix():
    """每条命中都必须能说清「为什么」和「怎么改」，并标明归哪一层处理。

    界面上只列规则名（S01 Rule of three）等于没说——用户无法判断
    该不该改、怎么改。explain / fix / handling 三样缺一不可。
    """
    import glob
    from diagnose import diagnose
    texts = [open(f, encoding="utf-8").read() for f in
             sorted(glob.glob("samples/*.txt")) + sorted(glob.glob("probe/bases/*.txt"))]
    texts.append("John (Jianqiu) Bai, Nicole Boyson, Yi Cao, Miao Liu, and Chi Wan\n\n"
                 "The framework serves as a pivotal tool, showcasing robust performance. "
                 "Overall, our results highlight the importance of this approach.")
    bad = []
    seen = set()
    for t in texts:
        for f in diagnose(t)["findings"]:
            seen.add(f["rule_id"])
            if not f.get("explain"):
                bad.append(f"{f['rule_id']}: 缺 explain")
            if not f.get("fix"):
                bad.append(f"{f['rule_id']}: 缺 fix（怎么改）")
            if f.get("handling") not in ("code", "llm", "report"):
                bad.append(f"{f['rule_id']}: handling='{f.get('handling')}'，"
                           f"必须是 code/llm/report 之一")
    assert not bad, "命中信息不完整:\n  " + "\n  ".join(sorted(set(bad)))


def test_author_list_not_flagged():
    """作者署名不是文风问题。

    真实论文第一页就是作者名单，「Yi Cao, Miao Liu, and Chi Wan」
    被判成 Rule of three 是明显误报，会让用户第一眼就不信任这个工具。
    """
    from diagnose import diagnose
    for line in ["John (Jianqiu) Bai, Nicole Boyson, Yi Cao, Miao Liu, and Chi Wan",
                 "We thank Alice Chen, Bob Smith, and Carol Wang for comments.",
                 "Experiments run on PeMS04, METR-LA, and NYC-Taxi datasets."]:
        hits = [f["rule_id"] for f in diagnose(line)["findings"] if f["rule_id"] == "S01"]
        assert not hits, f"专名枚举被误判为 S01：{line!r}"


def test_overall_never_reports_a_percentage():
    """整体评估绝不能出现「AI 率 X%」这种数字。

    产品设计里定死的一条：任何百分比都预测不了知网、维普会给多少分。
    我们说 40%、知网给 70%，用户会永久性地不再信任这个工具——
    一次失准毁掉的信任，靠后面多少次准确都补不回来。
    """
    import re
    from diagnose import diagnose
    o = diagnose("本文深入探讨了该问题，研究表明其具有重要的理论意义。")["overall"]
    blob = str(o)
    for pat in (r'AI\s*率', r'AI[- ]?rate', r'概率', r'置信度'):
        assert not re.search(pat, blob, re.I), f"整体评估里出现了 {pat}：{blob[:200]}"
    assert "百分比" in o["disclaimer"], "必须明确声明不给百分比"
    # 声明必须跟数据一起下发，换个前端也不能丢
    assert o["feature_caveat"] and o["disclaimer"]


def test_overall_feature_caveat_matches_measurement():
    """「特征数不能当分数读」这句话必须和实测数据一致。

    人类对照样本的句式特征密度如果不再高于 AI 样本，这句话就成了假话，
    必须跟着改——文案和数据必须同步，否则会变成我们自己编的说辞。
    """
    import glob
    import re as _re
    from diagnose import diagnose
    from rewrite import REPORT_ONLY

    def density(paths):
        tot = n = 0
        for f in paths:
            t = open(f, encoding="utf-8").read()
            tot += len([x for x in diagnose(t)["findings"]
                        if x["rule_id"] not in REPORT_ONLY["zh"]])
            n += len(_re.findall(r'[一-鿿]', t))
        return tot / n * 1000 if n else 0

    human = density(["samples/human_sample.txt"])
    ai = density(sorted(glob.glob("probe/bases/*.txt")))
    assert human > ai, (
        f"人类样本特征密度 {human:.2f} 不再高于 AI 样本 {ai:.2f}，"
        f"overall.py 里「特征数不能当分数读」的说明已与数据不符，必须更新")


def test_density_denominator_handles_chinese():
    """密度分母不能用 \\b\\w+\\b 数中文。

    Python 的 \\w 包含 CJK，而 \\b 只在中英交界处成立，
    整段中文会被算成两三个「词」，密度虚高几百倍——
    线上曾出现「句式特征 625/千字」这种明显荒谬的数字。
    """
    from diagnose import diagnose
    zh = "本文深入探讨了图神经网络在交通流预测中的应用。" * 20
    o = diagnose(zh)["overall"]
    assert 300 <= o["n_unit"] <= len(zh) + 10, f"中文当量字数算错：{o['n_unit']} vs 实际 {len(zh)}"
    assert o["feature_per_1k"] < 100, f"特征密度 {o['feature_per_1k']}/千字 明显失真"
    # 短文本必须标出不可信，而不是给一个会误导人的数字
    short = diagnose("研究表明该方法有效。")["overall"]
    assert not short["reliable"] and short["unreliable_note"]
