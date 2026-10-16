"""Humanizer-zh local MVP invariants."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import guard
import humanizer_cn as H
from normalize import normalize_text
from llm import MockClient
from llm import LLMError


def test_analyzer_contract():
    text = "本文将深入探讨一个至关重要的问题。"
    report = H.analyze(text)
    assert report["summary"]["checks"] == 31
    assert report["summary"]["findings"] >= 2
    assert "不是 AI 率" in report["disclaimer"]
    for f in report["findings"]:
        assert text[f["start"]:f["end"]] == f["matched"]
        assert f["reason"] and f["suggestion"]
        assert f["handling"] in {"safe", "rewrite", "review"}


def test_normalization_removes_only_targeted_invisible_characters():
    src = "公式 x²+y²=1，编号①，ＡＩ文本１２３含\u200b隐藏字符。"
    out, report = normalize_text(src)
    assert out == "公式 x²+y²=1，编号①，ＡＩ文本１２３含隐藏字符。"
    assert report["invisible"] == 1 and report["changed"]


def test_real_three_item_list_is_review_only():
    text = "系统新增导出、搜索和批量重命名。"
    hits = [f for f in H.analyze(text)["findings"] if f["pattern_id"] == "B6"]
    assert hits and all(f["handling"] == "review" for f in hits)
    fixed = H.autofix(text)
    assert fixed["text"] == text, "三项真实功能不得被机械删除或打散"


def test_safe_cleanup_preserves_facts():
    text = ('本次调查共收到 126 份问卷，其中 18 份未完成全部题目。'
            '**本文结论**保持不变。本文将深入探讨这个至关重要的问题。')
    result = H.autofix(text)
    assert "126" in result["text"] and "18" in result["text"] and "未完成" in result["text"]
    assert not result["guard"]["fabricated"]
    assert not result["guard"]["semantic_changed"]
    assert "**" not in result["text"] and "本文结论" in result["text"]
    assert "深入探讨" in result["text"] and "至关重要" in result["text"]


def test_guard_blocks_new_chinese_name():
    cmp = guard.compare("一名研究者参与测试。", "张伟参与测试。")
    assert cmp["fabricated"] and "张伟" in cmp["added"].get("专名", [])


def test_guard_blocks_semantic_boundary_changes():
    cases = [
        ("该方法可能有效。", "该方法有效。"),
        ("该展馆不对公众开放。", "该展馆对公众开放。"),
        ("面积超过 3000 平方米。", "面积等于 3000 平方米。"),
        ("使用时长与成绩相关。", "使用时长导致成绩下降。"),
        ("计划周五发布。", "周五已经发布。"),
        ("本方法在测试中不成功。", "本方法在测试中成功。"),
        ("该干预使风险降低。", "该干预使风险增加。"),
        ("模型A的指标高于模型B。", "模型A的指标低于模型B。"),
    ]
    for src, out in cases:
        cmp = guard.compare(src, out)
        assert cmp["semantic_changed"], (src, out, cmp)


def test_candidate_rejects_fabrication_and_certainty_shift():
    src = "该方法可能有效，目前尚未完成测试。本文将深入探讨其表现。"
    fabricated = H._candidate(src, src + "张伟的实验证明准确率为 97.3%。")
    assert not fabricated["ok"]
    certain = H._candidate(src, "该方法有效，已完成测试。本文讨论其表现。")
    assert not certain["ok"] and "语义边界" in certain["reason"]


def test_guard_binds_facts_to_their_subjects():
    cases = [
        ("A组有10人，B组有20人。", "A组有20人，B组有10人。"),
        ("方法A可能有效，方法B有效。", "方法A有效，方法B可能有效。"),
        ("变量A与结果相关，变量B导致结果变化。",
         "变量A导致结果变化，变量B与结果相关。"),
        ("教师影响学生的选择。", "学生影响教师的选择。"),
        ("A组有10人、B组有20人。", "A组有20人、B组有10人。"),
        ("模型A准确率为90%而模型B准确率为80%。",
         "模型A准确率为80%而模型B准确率为90%。"),
        ("参与者年龄10–20岁。", "参与者年龄20–10岁。"),
        ("在本项实验中，甲促进乙。", "在本项实验中，乙促进甲。"),
        ("北京有10人、上海有20人。", "北京有20人、上海有10人。"),
        ("男性有10人而女性有20人。", "男性有20人而女性有10人。"),
        ("苹果重10克、香蕉重20克。", "苹果重20克、香蕉重10克。"),
        ("药物按1:2配比制备。", "药物按2:1配比制备。"),
    ]
    for src, out in cases:
        cmp = guard.compare(src, out)
        assert cmp["semantic_changed"], (src, out, cmp)
        assert not H._candidate(src, out)["ok"]


def test_candidate_rejects_any_core_term_loss():
    src = "本文采用梯度下降算法完成模型训练，并报告训练结果。"
    out = "本文采用算法完成模型训练，并报告训练结果。"
    candidate = H._candidate(src, out)
    assert not candidate["ok"]
    assert "梯度" in candidate["reason"]


def test_candidate_rejects_limit_attribution_sign_and_unit_loss():
    cases = [
        ("值得注意的是，本方法仅适用于小样本数据。", "本方法适用于小样本数据。"),
        ("研究表明，本方法有效。", "本方法有效。"),
        ("本组剂量为10 mg。", "本组剂量为10 kg。"),
        ("第一次实验测得误差是-3.2。", "第一次实验测得误差是3.2。"),
        ("温度为10 ℃。", "温度为10 ℉。"),
        ("本次测得电压为10 mV。", "本次测得电压为10 mA。"),
        ("频率为10 MHz。", "频率为10 mHz。"),
        ("压力为10 kPa。", "压力为10 Pa。"),
        ("溶液浓度为10 mol/L。", "溶液浓度为10 mmol/L。"),
        ("两组间无显著差异。", "两组间存在显著差异。"),
        ("本研究尚无证据支持该结论。", "本研究的证据支持该结论。"),
        ("实验未见明显改善。", "实验出现明显改善。"),
        ("该结果排除了直接因果关系。", "该结果证明了直接因果关系。"),
        ("差异无统计学意义。", "差异具有统计学意义。"),
        ("该结果无临床意义。", "该结果具有临床意义。"),
        ("目前缺乏充分证据支持该研究结论。", "目前已有充分证据支持该研究结论。"),
        ("本次实验结果未显示两组间存在明显差异。",
         "本次实验结果清楚显示两组间存在明显差异。"),
        ("本研究纳入三组患者。", "本研究纳入四组患者。"),
        ("每名患者接受一次治疗。", "每名患者接受三次治疗。"),
        ("误差必须≤10%。", "误差必须≥10%。"),
        ("设定x<10时模型收敛。", "设定x>10时模型收敛。"),
        ("检验结果P＜0.05。", "检验结果P＞0.05。"),
        ("约束为 x ≤ y。", "约束为 x ≥ y。"),
        ("能量满足 E=mc²。", "能量满足 E≠mc²。"),
    ]
    for src, out in cases:
        cmp = guard.compare(src, out)
        assert cmp["fabricated"] or cmp["n_removed"] or cmp["semantic_changed"], \
            (src, out, cmp)
        assert not H._candidate(src, out)["ok"], (src, out, cmp)


def test_candidate_rejects_scientific_notation_changes():
    cases = [
        ("浓度为10⁻³ mol/L。", "浓度为10⁻² mol/L。"),
        ("阈值为1×10⁻³ A。", "阈值为1×10⁻⁴ A。"),
        ("误差为2.5e-4。", "误差为2.5e-3。"),
        ("浓度为10^-3 mol/L。", "浓度为10^-2 mol/L。"),
    ]
    for src, out in cases:
        candidate = H._candidate(src, out)
        assert not candidate["ok"], (src, out, candidate)


def test_normal_relation_paraphrases_remain_usable():
    cases = [
        ("值得注意的是，该方法能够促进学生学习。", "该方法可促进学生学习。"),
        ("值得注意的是，该因素会影响模型性能。", "该因素影响模型性能。"),
    ]
    for src, out in cases:
        candidate = H._candidate(src, out)
        assert candidate["ok"], (src, out, candidate)


def test_candidate_rejects_cross_paragraph_moves():
    cases = [
        (
            '值得注意的是，第一段详细讨论本文采用的研究方法与具体流程。\n\n'
            '第二段完整报告主要实验结果和相关观察。第三句进一步说明本研究现有局限。',
            '第一段详细讨论本文采用的研究方法与具体流程。'
            '第二段完整报告主要实验结果和相关观察。\n\n'
            '第三句进一步说明本研究现有局限。',
        ),
        (
            '值得注意的是，本文介绍研究内容和主要方法。随后说明分析过程。\n\n'
            '最后报告研究结果和实际效果。',
            '本文介绍研究内容和主要方法。\n\n'
            '随后说明分析过程。最后报告研究结果和实际效果。',
        ),
    ]
    for src, out in cases:
        candidate = H._candidate(src, out)
        assert not candidate["ok"], candidate
        assert "段" in candidate["reason"], candidate


def test_multi_paragraph_rewrites_stay_independent_and_usable():
    src = ('值得注意的是，该方法能够促进学生学习。\n\n'
           '值得注意的是，该因素会影响模型性能。')
    out = '该方法可促进学生学习。\n\n该因素影响模型性能。'
    candidate = H._candidate(src, out)
    assert candidate["ok"], candidate


def test_clear_text_can_remain_unchanged():
    text = "先保存文件，再关闭窗口。未保存的修改会丢失。"
    report = H.analyze(text)
    assert report["summary"]["findings"] == 0
    assert H.autofix(text)["text"] == text


def test_120k_noop_autofix_uses_fast_path():
    text = ("值得注意的是，本文将深入探讨这个至关重要的问题。"
            "两组间无显著差异，浓度为10 mol/L。\n\n" * 2600)[:120000]
    started = time.perf_counter()
    result = H.autofix(text)
    elapsed = time.perf_counter() - started
    assert result["text"] == text and not result["changed"]
    assert elapsed < 12, f"120k 无修改文本耗时 {elapsed:.2f}s"


def test_full_humanize_accepts_only_measurable_safe_improvement():
    src = "值得注意的是，该方法可能在小样本条件下有效，但目前尚未完成外部验证。"
    result = H.humanize(
        src,
        MockClient(lambda s: s.replace("值得注意的是，", "")),
        n_candidates=2,
    )
    assert result["text"] == "该方法可能在小样本条件下有效，但目前尚未完成外部验证。"
    assert result["n_accepted"] == 1
    assert result["guard"]["status"] == "passed"


def test_full_humanize_rejects_certainty_shift():
    src = "值得注意的是，该方法可能在小样本条件下有效，但目前尚未完成外部验证。"
    result = H.humanize(
        src,
        MockClient(lambda _s: "该方法已经证明有效。"),
        n_candidates=1,
    )
    assert result["text"] == src
    assert result["n_accepted"] == 0


def test_full_humanize_surfaces_model_failures():
    class BadClient(MockClient):
        def complete(self, *args, **kwargs):
            raise LLMError("401 invalid key")

    try:
        H.humanize("值得注意的是，该方法仍需验证。", BadClient(), n_candidates=1)
    except LLMError as exc:
        assert "401 invalid key" in str(exc)
    else:
        raise AssertionError("模型错误不应伪装成成功任务")


def test_formatting_and_protected_content_are_byte_preserved():
    src = ('第一行\n第二行\n\n```json\n{\"title\": \"深入探讨\"}\n```\n'
           '$x  \u2264  y$\n\u2211 x_i \u8868\u793a\u603b\u548c\u3002\n\u2192 \u8868\u793a\u6620\u5c04\u65b9\u5411\u3002')
    fixed = H.autofix(src)
    assert fixed["text"] == src
    result = H.humanize(src, MockClient(lambda s: s), n_candidates=1)
    assert result["text"] == src

    heading = H.autofix("## ✨ 研究方法")["text"]
    assert heading == "## 研究方法"
    indented = '    print("**重要**")\n'
    assert H.autofix(indented)["text"] == indented
    latex = r"值得注意的是，设 \(x \le y\)，则结论成立。"
    assert not H._candidate(latex, latex.replace(r"\le", r"\ge"))["ok"]


def test_title_repetition_checkpoint_is_reachable():
    text = "人工智能教育\n人工智能教育是本章讨论的主题。"
    hits = [f for f in H.analyze(text)["findings"] if f["pattern_id"] == "E24"]
    assert hits and hits[0]["handling"] == "review"


def test_long_document_chunks_batch_paragraphs_without_changing_separators():
    paragraph = "值得注意的是，该方法可能在小样本条件下有效，但尚未完成外部验证。"
    text = "\n\n".join([paragraph] * 300)
    chunks = H._chunks(text)
    assert "".join(part for part, _editable in chunks) == text
    editable = [part for part, is_editable in chunks if is_editable]
    assert len(editable) <= 5, f"300 段被拆成 {len(editable)} 次模型调用"

    formulas = "".join(
        f"值得注意的是，变量$x_{{{i}}}$具有重要作用。" for i in range(300))
    formula_chunks = H._chunks(formulas)
    assert "".join(part for part, _editable in formula_chunks) == formulas
    assert sum(1 for _part, editable in formula_chunks if editable) <= 5


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"✓ Humanizer-zh 引擎 {len(tests)} 项全部通过")
