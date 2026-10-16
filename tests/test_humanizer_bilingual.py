"""Product bilingual facade: stable v1 contract for Chinese and English."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import humanizer_bilingual as H  # noqa: E402
import rewrite as rewrite_engine  # noqa: E402
from llm import MockClient  # noqa: E402


def test_english_analysis_uses_english_rules():
    text = (
        "It was found that this study delves into a pivotal realm. "
        "The method may improve accuracy."
    )
    report = H.analyze(text)
    assert report["language"] == "en"
    assert report["summary"]["checks"] == 13
    assert report["summary"]["findings"] > 0
    assert any(item["pattern_id"] == "EN-S11" for item in report["findings"])
    assert "may" in [value.lower() for value in report["anchors"]["constraints"]]
    for item in report["findings"]:
        assert text[item["start"]:item["end"]] == item["matched"], item
        assert item["handling"] in {"safe", "rewrite", "review"}


def test_mixed_analysis_routes_each_paragraph():
    text = (
        "本文将深入探讨这一问题。\n\n"
        "It was found that the method may improve accuracy."
    )
    report = H.analyze(text)
    assert report["language"] == "mixed"
    assert report["language_counts"] == {"zh": 1, "en": 1}
    assert report["summary"]["checks"] == 44
    ids = {item["pattern_id"] for item in report["findings"]}
    assert "C12" in ids and "EN-S11" in ids, ids


def test_english_vocabulary_is_review_only():
    text = "This method utilizes available records."
    report = H.analyze(text)
    hit = next(item for item in report["findings"] if item["matched"] == "utilizes")
    assert hit["handling"] == "review"
    result = H.autofix(text)
    assert result["text"] == text
    assert not result["changed"]
    assert not result["guard"]["fabricated"]
    assert not result["guard"]["semantic_changed"]


def test_english_rewrite_preserves_qualifier_and_is_measurable():
    text = "It was found that the method may improve accuracy."
    client = MockClient(lambda _source: "The method may improve accuracy.")
    result = H.humanize(text, client, n_candidates=1)
    assert result["text"] == "The method may improve accuracy."
    assert result["n_chunks"] == 1 and result["n_accepted"] == 1
    assert result["guard"]["status"] == "passed"
    assert "may" in result["text"]
    assert client.calls == []


def test_short_passive_shell_can_be_removed_safely():
    text = "It was found that the method may improve accuracy."
    client = MockClient(lambda _source: "The method may improve accuracy.")
    result = H.humanize(text, client, n_candidates=1)
    assert result["text"] == "The method may improve accuracy."
    assert result["n_accepted"] == 1
    assert client.calls == []


def test_english_s11_ignores_free_form_semantic_changes():
    cases = [
        (
            "It was found that the method may improve accuracy.",
            "We found that the method improves accuracy.",
            "The method may improve accuracy.",
        ),
        (
            "It was found that the method did not improve accuracy.",
            "We found that the method improved accuracy.",
            "The method did not improve accuracy.",
        ),
    ]
    for source, unsafe, expected in cases:
        client = MockClient(lambda _text, value=unsafe: value)
        result = H.humanize(source, client, n_candidates=1)
        assert result["text"] == expected, (source, unsafe, result)
        assert result["n_accepted"] == 1
        assert client.calls == []


def test_english_s11_never_applies_model_body_addition_or_deletion():
    source = (
        "It was found that the method supports training and deployment "
        "across production environments."
    )
    unsafe = [
        "The method supports training across production environments.",
        "The method reliably supports advanced training and deployment "
        "across production environments.",
        "We found that the method supports training and deployment "
        "across production environments.",
    ]
    expected = (
        "The method supports training and deployment "
        "across production environments."
    )
    for candidate in unsafe:
        client = MockClient(lambda _text, value=candidate: value)
        result = H.humanize(
            source, client,
            n_candidates=1,
        )
        assert result["text"] == expected, (candidate, result)
        assert result["n_accepted"] == 1
        assert client.calls == []


def test_english_s11_validator_rejects_any_change_beyond_the_shell():
    source = "It was found that the method may improve accuracy."
    unsafe = "The method improves accuracy."
    scored = rewrite_engine._score_candidate(
        source,
        unsafe,
        "en",
        rewrite_engine.diagnose(source),
        None,
        target_rule_ids={"S11"},
    )
    assert scored["ok"] is False
    assert "被动壳之外" in scored["reason"]


def test_english_s11_preserves_case_sensitive_leading_identifiers():
    for identifier in ("miRNA", "k-means", "t-SNE", "a"):
        tail = "improved accuracy across all evaluated production environments and datasets."
        source = f"It was found that {identifier} {tail}"
        expected = f"{identifier} {tail}"
        changed_case = expected[0].upper() + expected[1:]
        client = MockClient(lambda _text, value=changed_case: value)
        result = H.humanize(
            source, client,
            n_candidates=1,
        )
        assert result["text"] == expected, (identifier, result)
        assert result["n_accepted"] == 1
        assert client.calls == []


def test_inline_bilingual_paragraph_is_detected_but_not_auto_rewritten():
    source = (
        "本文将深入探讨这个问题。 It was found that this method supports "
        "training and deployment across production environments."
    )
    report = H.analyze(source)
    assert report["language"] == "mixed"
    assert report["language_counts"] == {"zh": 1, "en": 1}
    ids = {item["pattern_id"] for item in report["findings"]}
    assert "C12" in ids and "EN-S11" in ids, ids

    client = MockClient(lambda _text: (
        "本文讨论这个问题。 This method supports training across production "
        "environments."
    ))
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == source
    assert result["n_accepted"] == 0
    assert client.calls == []


def test_chinese_paragraph_protects_comma_separated_latin_terms():
    source = "本文将深入探讨 bert、gpt、transformer 与 resnet 的应用。"
    unsafe = [
        "本文讨论 bert、gpt 与 resnet 的应用。",
        "本文讨论 bert、llama、transformer 与 resnet 的应用。",
    ]
    for candidate in unsafe:
        client = MockClient(lambda _text, value=candidate: value)
        result = H.humanize(source, client, n_candidates=1)
        assert result["text"] == source, (candidate, result)
        assert result["n_accepted"] == 0
        assert result["guard"]["status"] == "passed"
        assert client.calls == []


def test_chinese_paragraph_protects_unicode_and_identifier_tokens():
    cases = [
        (
            "本文将深入探讨 model_alpha、model_beta、model_gamma 的应用。",
            "本文讨论 model_alpha、model_gamma 的应用。",
        ),
        (
            "本文将深入探讨 model_alpha、model_beta、model_gamma 的应用。",
            "本文讨论 model_alpha、model_delta、model_gamma 的应用。",
        ),
        (
            "本文将深入探讨 model1 与 sha256 的应用。",
            "本文讨论 llama1 与 abc256 的应用。",
        ),
        (
            "本文将深入探讨 résumé 的处理。",
            "本文讨论 exposé 的处理。",
        ),
    ]
    for source, candidate in cases:
        client = MockClient(lambda _text, value=candidate: value)
        result = H.humanize(
            source, client,
            n_candidates=1,
        )
        assert result["text"] == source, (source, candidate, result)
        assert result["n_accepted"] == 0
        assert result["guard"]["status"] == "passed"
        assert client.calls == []


def test_chinese_paragraph_protects_latin_connector_syntax():
    cases = [
        ("本文将深入探讨 input/output pipeline 的设计。",
         "本文讨论 input output pipeline 的设计。"),
        ("本文将深入探讨 and/or policy 的设计。",
         "本文讨论 and or policy 的设计。"),
        ("本文将深入探讨 scikit.learn API 的应用。",
         "本文讨论 scikit learn API 的应用。"),
        ("本文将深入探讨 client/server architecture 的设计。",
         "本文讨论 client server architecture 的设计。"),
        ("本文将深入探讨 foo::bar API 的应用。",
         "本文讨论 foo bar API 的应用。"),
    ]
    for source, candidate in cases:
        client = MockClient(lambda _text, value=candidate: value)
        result = H.humanize(
            source, client,
            n_candidates=1,
        )
        assert result["text"] == source, (source, candidate, result)
        assert result["n_accepted"] == 0
        assert result["guard"]["status"] == "passed"
        assert client.calls == []


def test_chinese_latin_anchor_bindings_are_not_sent_to_monolingual_llm():
    cases = [
        (
            "本文将深入探讨使用 bert 进行训练、使用 gpt 进行部署的方法。",
            "本文讨论使用 bert 进行部署、使用 gpt 进行训练的方法。",
        ),
        (
            "本文将深入探讨 bert 负责训练而 gpt 负责部署的方法。",
            "本文讨论 bert 负责部署而 gpt 负责训练的方法。",
        ),
        (
            "本文将深入探讨 bert 影响精度、gpt 影响速度的机制。",
            "本文讨论 bert 影响速度、gpt 影响精度的机制。",
        ),
    ]
    for source, candidate in cases:
        client = MockClient(lambda _text, value=candidate: value)
        result = H.humanize(source, client, n_candidates=1)
        assert result["text"] == source
        assert result["n_accepted"] == 0
        assert client.calls == []


def test_chinese_explicit_label_bindings_cannot_be_swapped():
    cases = [
        ("甲负责训练、乙负责部署", "甲负责部署、乙负责训练"),
        ("甲用于训练、乙用于部署", "甲用于部署、乙用于训练"),
        ("甲采用方案一、乙采用方案二", "甲采用方案二、乙采用方案一"),
        ("甲处理图像、乙处理文本", "甲处理文本、乙处理图像"),
        ("甲对应训练集、乙对应测试集", "甲对应测试集、乙对应训练集"),
        ("甲承担训练、乙承担部署", "甲承担部署、乙承担训练"),
        ("甲生成图像、乙生成文本", "甲生成文本、乙生成图像"),
    ]
    for before, after in cases:
        source = f"本文将深入探讨{before}的方法。"
        candidate = f"本文讨论{after}的方法。"
        result = H.humanize(
            source, MockClient(lambda _text, value=candidate: value),
            n_candidates=1,
        )
        assert result["text"] == source, (source, candidate, result)
        assert result["n_accepted"] == 0


def test_english_content_deleting_rules_are_review_only():
    cases = [
        ("The system is efficient, ensuring transparent audit logs.",
         "transparent audit logs"),
        ("The method works, contributing to safe medical decisions.",
         "safe medical decisions"),
        ("The system is efficient, underscoring the importance of auditability.",
         "auditability"),
        ("The experiment failed. In conclusion, the model requires retraining before deployment.",
         "model requires retraining before deployment"),
        ("Overall, external synchronization remains disabled.",
         "external synchronization remains disabled"),
        ("Studies show that external synchronization remains disabled.",
         "Studies show that external synchronization remains disabled"),
        ("The cache acts as a temporary fallback.",
         "acts as a temporary fallback"),
    ]
    for source, protected in cases:
        report = H.analyze(source)
        risky = [item for item in report["findings"]
                 if item["pattern_id"] in {
                     "EN-S04", "EN-S05", "EN-S07", "EN-S08", "EN-P02",
                 }]
        assert risky and all(item["handling"] == "review" for item in risky), source
        fixed = H.autofix(source)
        assert protected in fixed["text"], (source, fixed)


def test_english_meaning_sensitive_vocabulary_is_review_only():
    source = (
        "The robust estimator significantly reduced error under a "
        "comprehensive sampling frame for the novel coronavirus."
    )
    report = H.analyze(source)
    vocab = [item for item in report["findings"]
             if item["pattern_id"] in {"EN-V-T1", "EN-V-T2"}]
    assert vocab and all(item["handling"] == "review" for item in vocab), vocab
    assert H.autofix(source)["text"] == source


def test_english_s11_never_uses_a_translated_model_candidate():
    source = "It was found that the method may improve accuracy."
    translated = "该方法可能提高准确率，研究人员已经确认了这一结果。"
    client = MockClient(lambda _text: translated)
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == "The method may improve accuracy."
    assert result["n_accepted"] == 1
    assert client.calls == []


def test_rule_of_three_is_review_only_and_cannot_drop_an_item():
    source = "The tool is fast, stable, and simple."
    report = H.analyze(source)
    hit = next(item for item in report["findings"] if item["pattern_id"] == "EN-S01")
    assert hit["handling"] == "review"
    client = MockClient(lambda _text: "The tool is fast and stable.")
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == source
    assert result["n_accepted"] == 0
    assert client.calls == []

    combined = (
        "It was found that the method supports training, deployment, "
        "monitoring, and maintenance."
    )
    client = MockClient(lambda _text: (
        "The method supports training, deployment, and monitoring."
    ))
    result = H.humanize(combined, client, n_candidates=1)
    assert result["text"] == (
        "The method supports training, deployment, monitoring, and maintenance."
    )
    assert result["n_accepted"] == 1
    assert client.calls == []


def test_s11_is_fixed_when_another_sentence_in_the_paragraph_has_s01():
    source = (
        "It was found that AI writing tools may improve editing efficiency. "
        "This study provides robust, comprehensive, and valuable insights."
    )
    expected = (
        "AI writing tools may improve editing efficiency. "
        "This study provides robust, comprehensive, and valuable insights."
    )
    report = H.analyze(source)
    ids = {item["pattern_id"] for item in report["findings"]}
    assert {"EN-S11", "EN-S01"} <= ids, ids

    client = MockClient(lambda _text: "unsafe model output must not be used")
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == expected
    assert result["n_chunks"] == 1
    assert result["n_accepted"] == 1
    assert result["guard"]["status"] == "passed"
    assert client.calls == []


def test_s11_in_later_sentence_is_fixed_without_touching_s01():
    source = (
        "The tool is fast, stable, and simple. "
        "It was found that the method may improve accuracy."
    )
    expected = (
        "The tool is fast, stable, and simple. "
        "The method may improve accuracy."
    )
    client = MockClient(lambda _text: "unsafe model output must not be used")
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == expected
    assert result["n_accepted"] == 1
    assert client.calls == []


def test_mixed_rewrite_keeps_paragraph_skeleton():
    text = (
        "这是已经清楚的中文段落。\n\n"
        "It was found that the method may improve accuracy."
    )
    client = MockClient(lambda source: (
        "The method may improve accuracy."
        if source.startswith("It was found") else source
    ))
    result = H.humanize(text, client, n_candidates=1)
    assert result["text"].count("\n\n") == 1
    assert result["text"].startswith("这是已经清楚的中文段落。\n\n")
    assert result["text"].endswith("The method may improve accuracy.")


def test_mixed_run_does_not_invent_document_edge_target():
    source = "让我们共同期待未来。\n\nThe tool is fast, stable, and simple."
    client = MockClient(lambda text: text.replace("共同", ""))
    result = H.humanize(source, client, n_candidates=1)
    assert result["text"] == source
    assert client.calls == []


def test_english_codefix_preserves_layout_and_list_capitalization():
    clear = "  The prose is already clear.\n\n\nNext paragraph.  "
    assert H.autofix(clear)["text"] == clear
    listed = "  - This method utilizes available records.  "
    fixed = H.autofix(listed)
    assert fixed["text"] == listed


def test_safe_only_humanize_reports_real_change_without_llm_acceptance():
    source = "**中文内容**"
    client = MockClient()
    result = H.humanize(source, client, n_candidates=1)
    assert result["changed"] is True
    assert result["n_safe_changes"] >= 1
    assert result["n_accepted"] == 0
    assert client.calls == []


def test_codefix_rollback_never_counts_as_an_accepted_safe_change():
    source = "研究表明该方法有效。\n\nThis prose is clear."
    fixed = H.autofix(source)
    assert fixed["text"] == source
    assert fixed["changed"] is False
    assert not any(item.get("accepted") for item in fixed["log"])


def test_mixed_format_findings_are_not_duplicated_and_paragraphs_are_one_based():
    formatted = H.analyze("**中文**\n\nThis prose is clear.")
    format_hits = [item for item in formatted["findings"]
                   if item["start"] == 0 and item["end"] <= len("**中文**")]
    assert len(format_hits) == 1, format_hits

    report = H.analyze(
        "本文将深入探讨这个问题。\n\n"
        "It was found that the method may improve accuracy."
    )
    assert {item["paragraph"] for item in report["findings"]} == {1, 2}
    assert report["summary"]["affected_paragraphs"] == 2


def test_chinese_with_many_latin_model_names_stays_chinese():
    text = "本文深入探讨 BERT, GPT, Transformer 与 ResNet-50 的应用。"
    report = H.analyze(text)
    assert report["language"] == "zh"
    assert any(item["pattern_id"] == "C12" for item in report["findings"])


def test_english_s11_does_not_call_a_failing_llm():
    class FailingClient(MockClient):
        def complete(self, *args, **kwargs):
            raise AssertionError("deterministic S11 path must not call the LLM")

    result = H.humanize(
        "It was found that the method may improve accuracy.",
        FailingClient(), n_candidates=1,
    )
    assert result["text"] == "The method may improve accuracy."
    assert result["n_accepted"] == 1


def test_opt_in_english_auto_rewrites_review_only_language():
    source = "Additionally, the method utilizes available records to support the analysis."
    client = MockClient(lambda _source: "The method uses available records to support the analysis.")
    phases = []
    result = H.humanize(source, client, n_candidates=1, auto_english=True,
                        stage=phases.append)
    assert result["text"] == "The method uses available records to support the analysis."
    assert result["n_chunks"] == result["n_accepted"] == 1
    assert len(client.calls) == 1
    assert result["after"]["summary"]["findings"] < result["before"]["summary"]["findings"]
    assert phases == ["checking", "finalizing"]


def test_opt_in_english_auto_rejects_factual_change():
    source = "Additionally, 126 students provided records for the analysis."
    client = MockClient(lambda _source: "A total of 200 students provided records for the analysis.")
    result = H.humanize(source, client, n_candidates=1, auto_english=True)
    assert result["text"] == source
    assert result["n_chunks"] == 1 and result["n_accepted"] == 0
    assert len(client.calls) == 1


def test_opt_in_english_auto_skips_ambiguous_enumeration():
    source = "The model is robust, comprehensive, and valuable."
    client = MockClient(lambda _source: "The model is robust and comprehensive.")
    result = H.humanize(source, client, n_candidates=1, auto_english=True)
    assert result["text"] == source
    assert result["n_chunks"] == 0
    assert client.calls == []


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"✓ 中英文分析、清理、改写与混排结构：{len(tests)} 项通过")
