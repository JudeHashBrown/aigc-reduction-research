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
import ssl
import urllib.error
import urllib.request
from typing import List, Optional


import re

# 不接受 temperature/top_p/top_k 的模型
_NO_SAMPLING = re.compile(
    r'(claude-)?(opus-5|opus-4-8|opus-4-7|sonnet-5|fable-5|mythos-5)', re.I)


class LLMError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url=None, api_key=None, model=None, temperature=None):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or ""
        self.model = model or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        self.temperature = float(temperature if temperature is not None
                                 else os.environ.get("LLM_TEMPERATURE", 0.85))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

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
        if n > 1:
            payload["n"] = n

        outs = self._call(payload, timeout)
        if len(outs) < n:                      # 服务端忽略了 n，退化为逐次调用
            payload.pop("n", None)
            while len(outs) < n:
                outs.extend(self._call(payload, timeout))
        return outs[:n]

    def _call(self, payload, timeout):
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        # 本地服务常用自签证书；仅在显式开启时放宽
        ctx = ssl._create_unverified_context() if os.environ.get("LLM_INSECURE") else None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout, context=ctx) if ctx else \
                 opener.open(req, timeout=timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"LLM 返回 {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except Exception as e:
            raise LLMError(f"LLM 调用失败: {e}")
        try:
            return [c["message"]["content"] for c in data["choices"]]
        except (KeyError, TypeError):
            raise LLMError(f"LLM 响应格式异常: {str(data)[:300]}")


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
