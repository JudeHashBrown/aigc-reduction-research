"""极简 OpenAI 兼容客户端。只用标准库 urllib，不引入 openai / requests。

配置（环境变量）：
    LLM_BASE_URL   例 https://api.openai.com/v1
    LLM_API_KEY
    LLM_MODEL      默认 gpt-4o-mini
    LLM_TEMPERATURE 默认 0.85

温度默认偏高是刻意的：降 AI 率需要输出有变化，低方差方向是反的。
BypassAIGC 用 reasoning=high 且不传 temperature，输出更收敛——那是错的方向。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl
import threading
import urllib.error
import urllib.request
from typing import List, Optional

import re

# 不接受 temperature/top_p/top_k 的模型
_NO_SAMPLING = re.compile(
    r'(claude-)?(opus-5|opus-4-8|opus-4-7|sonnet-5|fable-5|mythos-5)', re.I)


def _ssl_ctx():
    """macOS 上 python.org 版 Python 不带根证书，直连 HTTPS 会报
    CERTIFICATE_VERIFY_FAILED。优先用 certifi 的证书包。
    LLM_INSECURE=1 可跳过验证，仅用于自签证书的本地服务。"""
    if os.environ.get("LLM_INSECURE"):
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class LLMError(RuntimeError):
    pass


class _LLMHTTPError(LLMError):
    """保留 HTTP 状态与响应体，便于只对可确认的兼容性错误降级。"""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"LLM 返回 {status}: {body[:300]}")


def _does_not_support_n(status: int, body: str) -> bool:
    """仅识别「400 + 明确指向 n 参数不被支持」。

    不能只因为响应中出现一个字母 ``n`` 就重试；认证、配额、
    模型权限和其他请求错误必须原样上抛。
    """
    if status != 400 or not body:
        return False

    lowered = body.lower()
    explicit_n = bool(re.search(
        r"(?:parameter|param|field|property|body)[\s\[\].,:'\"`/_-]*n(?:\b|['\"`\]])"
        r"|(?:['\"`]n['\"`])\s*(?:parameter|param|field|property)"
        r"|参数\s*[`‘’'\"]?n[`‘’'\"]?",
        lowered,
    ))
    unsupported = bool(re.search(
        r"not\s+supported|unsupported|not\s+allowed|not\s+permitted|"
        r"unknown\s+(?:parameter|param|field)|unrecogni[sz]ed|unexpected|"
        r"extra[_\s-]*(?:forbidden|input|field)|additional\s+propert|"
        r"不支持|不允许|未知参数|无法识别",
        lowered,
    ))
    return explicit_n and unsupported


class Client:
    def __init__(self, base_url=None, api_key=None, model=None, temperature=None):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or ""
        self.model = model or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        self._ignores_n = False        # 服务端是否拒绝/忽略 n，首次调用后确定
        self.temperature = float(temperature if temperature is not None
                                 else os.environ.get("LLM_TEMPERATURE", 0.85))
        # A single Client is shared by the parallel candidate requests.  Keep
        # provider-reported usage cumulative and guarded by a lock so billing
        # diagnostics do not lose increments when several calls finish at once.
        self._usage_lock = threading.Lock()
        self._usage = {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @staticmethod
    def _safe_token_count(value) -> int:
        """Return a non-negative provider usage value without trusting types."""
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    def _record_usage(self, usage) -> None:
        """Aggregate OpenAI-compatible and Responses-style usage shapes."""
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = self._safe_token_count(
            usage.get("input_tokens", usage.get("prompt_tokens")))
        output_tokens = self._safe_token_count(
            usage.get("output_tokens", usage.get("completion_tokens")))
        total_tokens = self._safe_token_count(usage.get("total_tokens"))
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        with self._usage_lock:
            self._usage["requests"] += 1
            self._usage["input_tokens"] += input_tokens
            self._usage["output_tokens"] += output_tokens
            self._usage["total_tokens"] += total_tokens

    def usage_summary(self) -> dict:
        """Snapshot usage accumulated by this client instance."""
        with self._usage_lock:
            return dict(self._usage)

    def complete(self, system: str, user: str, n: int = 1,
                 max_tokens: int = 2000, timeout: int = 90) -> List[str]:
        """返回 n 个候选。服务端不支持 n>1 时自动退化为多次独立调用。"""
        if not self.configured:
            raise LLMError("未配置 LLM。请设置环境变量 LLM_BASE_URL 与 LLM_API_KEY。")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
        }
        # Claude 5 系列（Opus 5 / Sonnet 5 / Fable 5.x）已移除采样参数，
        # 传 temperature 会返回 400。这类模型靠多次独立调用获得候选多样性。
        if not _NO_SAMPLING.search(self.model):
            payload["temperature"] = self.temperature
        # 一旦发现服务端忽略 n，就记住，后续整篇文档都直接全并行发
        # ——否则每段都要先白白串行一次，一篇百段的论文多花十几分钟。
        if n > 1 and not self._ignores_n:
            payload["n"] = n

        if n > 1 and self._ignores_n:
            outs = self._parallel(payload, n, timeout)
        else:
            try:
                outs = self._call(payload, timeout)
            except _LLMHTTPError as exc:
                if (n > 1 and "n" in payload
                        and _does_not_support_n(exc.status, exc.body)):
                    # 有些 OpenAI 兼容端点明确拒绝 n。记住这个能力差异，
                    # 当前请求也直接改为 n 次无 n 的并发请求。
                    self._ignores_n = True
                    payload.pop("n", None)
                    outs = self._parallel(payload, n, timeout)
                else:
                    raise
            if n == 1 and not outs:
                raise LLMError("LLM 响应中没有候选文本")
            if len(outs) < n:
                self._ignores_n = True
        if len(outs) < n:
            payload.pop("n", None)
            outs.extend(self._parallel(payload, n - len(outs), timeout))
        if len(outs) < n:
            raise LLMError(f"LLM 候选不足：期望 {n} 个，实际 {len(outs)} 个")
        return outs[:n]

    def _parallel(self, payload, k, timeout):
        """并发发 k 次独立调用。

        服务端不支持 n>1 时的唯一正确做法：串行会把每段耗时乘 k，
        实测单次 8.9s、串行三次 23.8s，一篇百段的论文差出十几分钟。
        """
        payload = dict(payload)
        payload.pop("n", None)
        outs = []
        with ThreadPoolExecutor(max_workers=min(k, 4)) as pool:
            futs = [pool.submit(self._call, dict(payload), timeout) for _ in range(k)]
            for f in as_completed(futs):
                # 任意一次认证、配额、限流或网络失败都必须上抛。
                # 吞掉错误会让上层把不完整候选误报为成功。
                outs.extend(f.result())
        return outs

    def _call(self, payload, timeout):
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),                 # 绕过本机代理
            urllib.request.HTTPSHandler(context=_ssl_ctx()))
        try:
            with opener.open(req, timeout=timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            raise _LLMHTTPError(e.code, body) from e
        except Exception as e:
            raise LLMError(f"LLM 调用失败: {e}")
        # Record a successful provider call even when it returned no usage or
        # an unusable choices shape: the upstream request may still have cost.
        self._record_usage(data.get("usage") if isinstance(data, dict) else None)
        try:
            outputs = [c["message"]["content"] for c in data["choices"]]
        except (KeyError, TypeError):
            raise LLMError(f"LLM 响应格式异常: {str(data)[:300]}")
        if not outputs or any(not isinstance(item, str) or not item.strip()
                              for item in outputs):
            raise LLMError("LLM 响应中没有候选文本")
        return outputs


class MockClient(Client):
    """无密钥时用于跑通与测试流水线。不做任何真实改写。"""
    configured = True

    def __init__(self, transform=None):
        super().__init__(base_url="mock", api_key="mock")
        self.transform = transform or (lambda s: s)
        self.calls = []

    def complete(self, system, user, n=1, **kw):
        self.calls.append({"system": system, "user": user, "n": n})
        src = user.split("<<<TEXT>>>")[-1].split("<<<END>>>")[0].strip()
        return [self.transform(src) for _ in range(n)]
