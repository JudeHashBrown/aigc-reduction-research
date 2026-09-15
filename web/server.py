"""本地诊断服务。只用 Python 标准库，无需 pip install。

    python3 web/server.py          # 默认 http://127.0.0.1:8765
    python3 web/server.py 9000     # 指定端口
"""
import json
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))
sys.path.insert(0, str(ROOT.parent / "probe"))

from diagnose import diagnose          # noqa: E402
from codefix import codefix as autofix     # noqa: E402
from rewrite import pipeline as llm_pipeline  # noqa: E402
from llm import Client, LLMError           # noqa: E402

WEIGHTS = ROOT.parent / "engine" / "weights.json"
MAX_CHARS = 20000


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/health":
            self._send(200, json.dumps({"ok": True}))
        elif self.path == "/api/config":
            c = Client()
            self._send(200, json.dumps({
                "llm_configured": c.configured,
                "llm_model": c.model if c.configured else None,
                "calibrated": WEIGHTS.exists(),
            }, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            self._handle_post()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print("\n[请求处理失败]\n" + tb, flush=True)   # 控制台留痕，便于排查
            try:
                self._send(500, json.dumps({"error": "服务端处理失败，详见终端输出",
                                            "detail": tb.strip().splitlines()[-1]},
                                           ensure_ascii=False))
            except Exception:
                pass

    def _handle_post(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, json.dumps({"error": "请求体不是合法 JSON"},
                                              ensure_ascii=False))
        # 类型必须校验：传 [] 或 {"text": 123} 都会在下面炸成 500，
        # 而那是客户端错误，应该回 400。
        if not isinstance(payload, dict):
            return self._send(400, json.dumps({"error": "请求体必须是 JSON 对象"},
                                              ensure_ascii=False))
        raw = payload.get("text")
        if raw is not None and not isinstance(raw, str):
            return self._send(400, json.dumps({"error": "text 字段必须是字符串"},
                                              ensure_ascii=False))
        # 去掉控制字符：Word/PDF 粘贴常带 \x00 之类，会污染偏移与输出
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw or "")[:MAX_CHARS]
        if not text.strip():
            return self._send(400, json.dumps({"error": "文本为空"}, ensure_ascii=False))

        wp = str(WEIGHTS) if WEIGHTS.exists() else None
        if self.path == "/api/diagnose":
            r = diagnose(text, weights_path=wp)
            r["text"] = text
            r["calibrated"] = WEIGHTS.exists()
            return self._send(200, json.dumps(r, ensure_ascii=False))

        if self.path == "/api/autofix":
            fixed, log = autofix(text)
            before = diagnose(text, weights_path=wp)
            after = diagnose(fixed, weights_path=wp)
            return self._send(200, json.dumps({
                "fixed_text": fixed, "log": log,
                "before": before["summary"], "after": after["summary"],
                "after_full": after, "text": fixed,
            }, ensure_ascii=False))

        if self.path == "/api/rewrite":
            client = Client()
            if not client.configured:
                return self._send(400, json.dumps({
                    "error": "未配置 LLM。请设置环境变量 LLM_BASE_URL 和 LLM_API_KEY 后重启服务。"
                }, ensure_ascii=False))
            n = int(payload.get("n") or 3)
            mx = payload.get("max_paragraphs")
            r = llm_pipeline(text, client, n_candidates=max(1, min(n, 5)),
                             weights_path=wp,
                             max_paragraphs=int(mx) if mx else None)
            return self._send(200, json.dumps(r, ensure_ascii=False))

        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass                      # 静音访问日志


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    url = f"http://127.0.0.1:{port}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"无法在端口 {port} 启动：{e}")
        print(f"多半是端口被占用。换一个端口试试：python3 web/server.py {port + 1}")
        sys.exit(1)
    print(f"诊断服务已启动 → {url}")
    print(f"权重：{'已标定 weights.json' if WEIGHTS.exists() else '临时权重（未经探测标定）'}")
    _c = Client()
    print(f"LLM ：{_c.model + ' 已就绪' if _c.configured else '未配置（只有规则层可用）'}"
          + ("" if _c.configured else "\n      设置 LLM_BASE_URL 与 LLM_API_KEY 后重启即可启用改写层"))
    import os
    if any(os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY")):
        print("提示：检测到系统代理。若浏览器打不开或诊断报错，")
        print("     请在代理软件/浏览器里把 127.0.0.1、localhost 加入绕过列表。")
    print("Ctrl+C 停止")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
