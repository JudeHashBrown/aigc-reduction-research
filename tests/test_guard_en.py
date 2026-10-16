"""英文事实守卫回归测试。

这里不测文风是否“更好”，只测学术润色绝不能静默改变的边界：
否定、确定程度、相关/因果、计划/完成状态、条件、范围和比较方向。
"""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import guard  # noqa: E402


def assert_blocked(source: str, rewritten: str, expected_key: str):
    result = guard.compare(source, rewritten, "en")
    assert result["semantic_changed"], (source, rewritten, result)
    assert expected_key in result["semantic"]["changed"], (
        expected_key, source, rewritten, result["semantic"]["changed"])


def assert_allowed(source: str, rewritten: str):
    result = guard.compare(source, rewritten, "en")
    assert not result["semantic_changed"], (
        source, rewritten, result["semantic"]["changed"])


def test_uncertainty_and_negation_are_preserved():
    assert_blocked(
        "The method may improve accuracy.",
        "The method improves accuracy.",
        "不确定性",
    )
    assert_blocked(
        "The system does not support public access.",
        "The system supports public access.",
        "否定",
    )
    assert_blocked(
        "The model doesn't include external data.",
        "The model includes external data.",
        "否定",
    )
    assert_blocked(
        "The model can’t be used without approval.",
        "The model can be used with approval.",
        "否定",
    )


def test_correlation_cannot_be_upgraded_to_causation():
    assert_blocked(
        "Study time is correlated with test performance.",
        "Study time causes test performance.",
        "关系强化",
    )
    assert_blocked(
        "Variable X is associated with outcome Y.",
        "Variable X leads to outcome Y.",
        "关系强化",
    )


def test_plan_and_future_cannot_become_completed_work():
    assert_blocked(
        "We plan to release the model next year.",
        "We released the model next year.",
        "计划状态",
    )
    assert_blocked(
        "The team intends to validate the dataset.",
        "The team completed validation of the dataset.",
        "完成状态",
    )
    assert_blocked(
        "The results will be published after review.",
        "The results were published after review.",
        "计划状态",
    )


def test_conditions_scope_modality_and_comparisons_are_preserved():
    cases = [
        (
            "If the sample is valid, the method may be used.",
            "The sample is valid, and the method may be used.",
            "条件",
        ),
        (
            "The sample must contain at least 100 records.",
            "The sample must contain at most 100 records.",
            "数量边界",
        ),
        (
            "The value is greater than 10%.",
            "The value equals 10%.",
            "数量边界",
        ),
        (
            "All participants must respond.",
            "Some participants must respond.",
            "全称范围",
        ),
        (
            "Participants must respond.",
            "Participants should respond.",
            "义务强度",
        ),
        (
            "The score is higher than baseline.",
            "The score is lower than baseline.",
            "高比较",
        ),
        (
            "Only enrolled students can participate.",
            "Enrolled students participate.",
            "唯一范围",
        ),
    ]
    for source, rewritten, expected_key in cases:
        assert_blocked(source, rewritten, expected_key)


def test_equivalent_english_boundary_paraphrases_remain_usable():
    cases = [
        ("The method may improve accuracy.", "The method might improve accuracy."),
        ("The system does not support public access.",
         "The system cannot support public access."),
        ("X is correlated with Y.", "X is associated with Y."),
        ("We plan to release the model.", "We intend to release the model."),
        ("The value is at least 10%.", "The value is no less than 10%."),
        ("If the sample is valid, the model can run.",
         "Provided that the sample is valid, the model is able to run."),
        ("All participants must respond.", "Every participant is required to respond."),
        ("The score is higher than baseline.", "The score is greater than baseline."),
    ]
    for source, rewritten in cases:
        assert_allowed(source, rewritten)


def test_chinese_default_path_still_uses_existing_markers():
    changed = guard.compare("该方法可能有效。", "该方法有效。")
    assert changed["semantic_changed"]
    assert "不确定性" in changed["semantic"]["changed"]

    equivalent = guard.compare("该方法可能有效。", "该方法或许有效。")
    assert not equivalent["semantic_changed"], equivalent["semantic"]["changed"]


if __name__ == "__main__":
    tests = [value for key, value in sorted(globals().items())
             if key.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"✓ 英文事实守卫 {len(tests)} 项全部通过")
