"""LLM 层对抗测试：模拟模型的各种实际失效模式。

模型不会永远乖乖只输出正文。真实会遇到：套 markdown 代码块、加前言、
复述指令、语言跑偏、输出空、把提示词回显出来、编造事实。
这些都必须被拦住或清理，不能污染最终文本。
"""
import io
import json
import sys
import threading
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "probe"))

import rewrite
import llm as llm_module
from llm import Client, LLMError, MockClient, _LLMHTTPError

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


def test_unsupported_n_400_falls_back_to_parallel_calls():
    """端点明确拒绝 n 时，当前请求并发降级，后续直接走降级路径。"""
    class FakeResponse:
        def __init__(self, content):
            self._body = json.dumps({
                "choices": [{"message": {"content": content}}]
            }).encode("utf-8")

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEndpoint:
        def __init__(self):
            self.lock = threading.Lock()
            self.calls = []
            self.active = 0
            self.max_active = 0

        def open(self, req, timeout=None):
            payload = json.loads(req.data.decode("utf-8"))
            with self.lock:
                self.calls.append(payload)
                call_no = len(self.calls)
            if "n" in payload:
                body = json.dumps({
                    "error": {
                        "message": "Unsupported parameter: 'n' is not supported.",
                        "param": "n",
                        "code": "unsupported_parameter",
                    }
                }).encode("utf-8")
                raise urllib.error.HTTPError(
                    req.full_url, 400, "Bad Request", {}, io.BytesIO(body))

            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.03)
            with self.lock:
                self.active -= 1
            return FakeResponse(f"candidate-{call_no}")

    endpoint = FakeEndpoint()
    original = llm_module.urllib.request.build_opener
    llm_module.urllib.request.build_opener = lambda *args, **kwargs: endpoint
    try:
        client = Client(base_url="https://compat.example/v1", api_key="test")
        got = client.complete("system", "user", n=3)
        assert len(got) == 3
        assert endpoint.calls[0]["n"] == 3
        assert all("n" not in p for p in endpoint.calls[1:])
        assert endpoint.max_active >= 2, "降级后应并发请求候选"
        assert client._ignores_n

        previous = len(endpoint.calls)
        assert len(client.complete("system", "user", n=2)) == 2
        assert len(endpoint.calls) == previous + 2
        assert all("n" not in p for p in endpoint.calls[previous:])
    finally:
        llm_module.urllib.request.build_opener = original


def test_non_n_errors_are_not_retried():
    """认证、配额、其他 400 与网络错误都不得被误当成 n 降级。"""
    cases = [
        _LLMHTTPError(401, '{"error":{"code":"invalid_api_key"}}'),
        _LLMHTTPError(429, '{"error":{"code":"insufficient_quota"}}'),
        _LLMHTTPError(400, "Unsupported parameter: 'max_tokens'"),
        LLMError("LLM 调用失败: connection reset"),
    ]

    for expected in cases:
        class FailingClient(Client):
            def __init__(self):
                super().__init__(base_url="https://compat.example/v1", api_key="test")
                self.calls = 0

            def _call(self, payload, timeout):
                self.calls += 1
                raise expected

        client = FailingClient()
        try:
            client.complete("system", "user", n=3)
        except LLMError as actual:
            assert actual is expected
        else:
            raise AssertionError(f"{expected!r} 未上抛")
        assert client.calls == 1, f"{expected!r} 被错误重试"
        assert not client._ignores_n


def test_parallel_candidate_error_is_not_swallowed():
    """降级并发中任一请求失败，整个调用必须失败而非返回部分候选。"""
    class PartiallyFailingClient(Client):
        def __init__(self):
            super().__init__(base_url="https://compat.example/v1", api_key="test")
            self._ignores_n = True
            self.lock = threading.Lock()
            self.calls = 0

        def _call(self, payload, timeout):
            with self.lock:
                self.calls += 1
                call_no = self.calls
            if call_no == 1:
                raise LLMError("LLM 调用失败: timeout")
            return [f"candidate-{call_no}"]

    client = PartiallyFailingClient()
    try:
        client.complete("system", "user", n=3)
    except LLMError as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError("并发请求的 LLMError 被吞掉")
    assert client.calls == 3, "候选请求只应各发一次"


def test_empty_choices_is_an_operational_error():
    """HTTP 200 但 choices=[] 不得被上层误报为 0 个候选的成功任务。"""
    class EmptyClient(Client):
        def __init__(self):
            super().__init__(base_url="https://compat.example/v1", api_key="test")
            self.calls = 0

        def _call(self, payload, timeout):
            self.calls += 1
            return []

    client = EmptyClient()
    try:
        client.complete("system", "user", n=1)
    except LLMError as exc:
        assert "没有候选文本" in str(exc)
    else:
        raise AssertionError("choices=[] 被误报为成功")
    assert client.calls == 1


def test_blank_choice_content_is_an_operational_error():
    """choices 占位但 content 为 null/空串也不是成功候选。"""
    class FakeResponse:
        def __init__(self, content):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()

    original = llm_module.urllib.request.build_opener
    try:
        for bad in (None, "", "   \n"):
            class FakeOpener:
                def open(self, req, timeout=None):
                    return FakeResponse(bad)

            llm_module.urllib.request.build_opener = lambda *args, **kwargs: FakeOpener()
            client = Client(base_url="https://compat.example/v1", api_key="test")
            try:
                client.complete("system", "user", n=1)
            except LLMError as exc:
                assert "没有候选文本" in str(exc)
            else:
                raise AssertionError(f"content={bad!r} 被误报为成功")
    finally:
        llm_module.urllib.request.build_opener = original
