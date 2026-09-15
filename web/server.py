"""本地诊断服务。只用 Python 标准库，无需 pip install。

    python3 web/server.py          # 默认 http://127.0.0.1:8765
    python3 web/server.py 9000     # 指定端口
"""
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))
sys.path.insert(0, str(ROOT.parent / "probe"))

from diagnose import diagnose          # noqa: E402
from ablations import ABLATIONS           # noqa: E402
from ablations_en import ABLATIONS_EN     # noqa: E402
from diagnose import detect_lang          # noqa: E402

WEIGHTS = ROOT.parent / "engine" / "weights.json"
MAX_CHARS = 20000


def autofix(text):
    """确定性修复：只跑不需要语义理解的变换，逐条记录改了什么。

    按段落识别语言，中英各用各的变换集——中文论文配英文摘要是常见形态，
    只修中文等于放着一半不管。

    这是「代码优先」架构的体现：毫秒级、可复现、不经过任何模型，
    因此不会反向注入 AI 统计特征。
    """
    import re
    SAFE_ZH = ["V-T1", "V-T2", "S05", "S07", "S08", "S04", "S03", "S01", "F01", "F02"]
    SAFE_EN = ["V-T1", "V-T2", "S05", "S07", "S08", "S04", "S03", "P02", "F01"]
    tally, out_paras = {}, []

    for para in text.split("\n"):
        if not para.strip():
            out_paras.append(para)
            continue
        lang = detect_lang(para)
        table = ABLATIONS_EN if lang == "en" else ABLATIONS
        safe = SAFE_EN if lang == "en" else SAFE_ZH
        cur = para
        for rid in safe:
            if rid not in table:
                continue
            name, fn = table[rid]
            new, n = fn(cur)
            if n and new.strip() != cur.strip():
                key = (rid, name, lang)
                tally[key] = tally.get(key, 0) + n
                cur = new
        out_paras.append(cur)

    fixed = "\n".join(out_paras)
    fixed = re.sub(r'[ \t]+\n', '\n', fixed)
    fixed = re.sub(r'\n{3,}', '\n\n', fixed).strip()
    log = [{"rule_id": k[0], "name": k[1], "lang": k[2], "count": v}
           for k, v in sorted(tally.items(), key=lambda kv: -kv[1])]
    return fixed, log


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
            return self._send(400, json.dumps({"error": "bad json"}))
        text = (payload.get("text") or "")[:MAX_CHARS]
        if not text.strip():
            return self._send(400, json.dumps({"error": "empty text"}))

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
