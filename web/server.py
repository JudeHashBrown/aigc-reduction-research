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
import base64
from normalize import normalize_text, describe as describe_norm
import docx_io
from llm import Client, LLMError           # noqa: E402

WEIGHTS = ROOT.parent / "engine" / "weights.json"
# 硕士论文正文常在 3-8 万字。2 万的旧上限会把整篇论文截断一半，
# 而截断是静默发生的，用户拿到的报告只覆盖前半篇。
MAX_CHARS = 120000
MAX_BODY_BYTES = 64 * 1024 * 1024      # 请求体上限（docx 走 base64，约 1.37 倍膨胀）


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
        if n > MAX_BODY_BYTES:
            return self._send(413, json.dumps({"error": "请求体过大"}, ensure_ascii=False))
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
        # docx 接口不走文本路径，先分流
        if self.path.startswith("/api/docx/"):
            return self._handle_docx(payload)

        # 归一化：零宽字符会让**全部规则失效**，必须在诊断之前清掉。
        # 清掉了什么要如实告诉用户——那本身就是有价值的信息。
        text, norm = normalize_text(raw or "")
        truncated = len(text) > MAX_CHARS
        text = text[:MAX_CHARS]
        if not text.strip():
            return self._send(400, json.dumps({"error": "文本为空"}, ensure_ascii=False))
        notices = describe_norm(norm)
        if truncated:
            notices.insert(0, {"level": "warn",
                               "text": f"文本超过 {MAX_CHARS} 字上限，只处理了前 {MAX_CHARS} 字。"})

        wp = str(WEIGHTS) if WEIGHTS.exists() else None
        if self.path == "/api/diagnose":
            r = diagnose(text, weights_path=wp)
            r["text"] = text
            r["calibrated"] = WEIGHTS.exists()
            r["notices"] = notices
            return self._send(200, json.dumps(r, ensure_ascii=False))

        if self.path == "/api/autofix":
            fixed, log = autofix(text)
            before = diagnose(text, weights_path=wp)
            after = diagnose(fixed, weights_path=wp)
            return self._send(200, json.dumps({
                "fixed_text": fixed, "log": log,
                "before": before["summary"], "after": after["summary"],
                "after_full": after, "text": fixed, "notices": notices,
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
            r["notices"] = notices
            return self._send(200, json.dumps(r, ensure_ascii=False))

        self._send(404, json.dumps({"error": "not found"}))

    def _handle_docx(self, payload):
        """docx 出入口。原始文件字节由前端保管并回传，服务端不存会话状态。"""
        b64 = payload.get("file")
        if not isinstance(b64, str) or not b64:
            return self._send(400, json.dumps({"error": "缺少 file 字段（base64 编码的 .docx）"},
                                              ensure_ascii=False))
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception:
            return self._send(400, json.dumps({"error": "file 不是合法的 base64"},
                                              ensure_ascii=False))

        if self.path == "/api/docx/extract":
            try:
                text, meta = docx_io.extract(data)
            except docx_io.DocxError as exc:
                return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))
            clean, norm = normalize_text(text)
            notices = describe_norm(norm)
            if meta.get("has_tables"):
                notices.append({"level": "info",
                                "text": "文档含表格。表格内的文字已一并提取，"
                                        "但导出时表格结构保持不变。"})
            if len(clean) > MAX_CHARS:
                notices.insert(0, {"level": "warn",
                                   "text": f"正文 {len(clean)} 字，超过 {MAX_CHARS} 字上限。"})
            meta.pop("para_map", None)          # 下标由服务端在导出时重算，不外传
            return self._send(200, json.dumps({"text": clean, "meta": meta,
                                               "notices": notices}, ensure_ascii=False))

        if self.path == "/api/docx/export":
            new_text = payload.get("text")
            if not isinstance(new_text, str) or not new_text.strip():
                return self._send(400, json.dumps({"error": "缺少 text 字段"},
                                                  ensure_ascii=False))
            try:
                _, meta = docx_io.extract(data)
                paras = [p.strip() for p in new_text.split("\n\n") if p.strip()]
                out = docx_io.replace(data, paras, meta)
            except docx_io.DocxError as exc:
                # 段落数对不上时宁可报错也不写回——错位会毁掉整篇论文
                return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))
            return self._send(200, json.dumps({
                "file": base64.b64encode(out).decode(),
                "n_paragraphs": len(paras),
            }, ensure_ascii=False))

        return self._send(404, json.dumps({"error": "not found"}))

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
    print(f"诊断服务已启动 → {url}", flush=True)
    print(f"权重：{'已标定 weights.json' if WEIGHTS.exists() else '临时权重（未经探测标定）'}")
    _c = Client()
    print(f"LLM ：{_c.model + ' 已就绪' if _c.configured else '未配置（只有规则层可用）'}"
          + ("" if _c.configured else "\n      设置 LLM_BASE_URL 与 LLM_API_KEY 后重启即可启用改写层"))
    import os
    if any(os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY")):
        print("提示：检测到系统代理。若浏览器打不开或诊断报错，")
        print("     请在代理软件/浏览器里把 127.0.0.1、localhost 加入绕过列表。")
    print("Ctrl+C 停止", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
