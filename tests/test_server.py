"""服务端接口测试：确保任何输入都返回合法 JSON，不挂、不 500。"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8799
FAILS = []
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(path, payload, timeout=40):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return op.open(req, timeout=timeout).status, json.loads(op.open(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"_raw": body[:200].decode("utf-8", "replace")}


proc = subprocess.Popen([sys.executable, str(ROOT / "web/server.py"), str(PORT)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(3)
try:
    for path in ["/", "/health", "/api/config"]:
        try:
            r = op.open(f"http://127.0.0.1:{PORT}{path}", timeout=8)
            if r.status != 200:
                FAILS.append(f"GET {path} → {r.status}")
        except Exception as e:
            FAILS.append(f"GET {path} 失败: {e}")

    CASES = {
        "正常": "本文深入探讨了该问题，综上所述，具有重要意义。",
        "空": "",
        "空白": "   \n  ",
        "超长": "本文深入探讨了该问题。" * 400,
        "正则字符": "研究 f(x)=a*b+c[i]|d 的性质，具有重要意义。",
        "CRLF": "第一段。\r\n\r\n第二段，具有重要意义。",
        "纯英文": "This delves into a pivotal realm, underscoring the importance of it.",
        "emoji": "本文🔬深入探讨，具有重要意义。",
        "超长单词": "a" * 5000,
        "控制字符": "本文\x00\x08深入探讨，具有重要意义。",
    }
    for name, text in CASES.items():
        for api in ["/api/diagnose", "/api/autofix"]:
            try:
                code, body = post(api, {"text": text})
            except Exception as e:
                FAILS.append(f"{api} [{name}] 异常: {type(e).__name__}: {e}")
                continue
            if not isinstance(body, dict):
                FAILS.append(f"{api} [{name}] 返回非对象")
            elif code >= 500:
                FAILS.append(f"{api} [{name}] → {code}: {str(body)[:110]}")
            elif code == 400 and not body.get("error"):
                FAILS.append(f"{api} [{name}] 400 但无 error 字段")
            elif code == 200 and "summary" not in body and "before" not in body:
                FAILS.append(f"{api} [{name}] 200 但缺关键字段: {list(body)[:5]}")

    # 畸形请求
    for bad in [b"not json", b"", b"[]", b'{"text": 123}', b'{"nope": 1}']:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/diagnose", data=bad,
                                     headers={"Content-Type": "application/json"})
        try:
            op.open(req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                FAILS.append(f"畸形请求 {bad[:18]!r} → {e.code}（应为 4xx）")
        except Exception as e:
            FAILS.append(f"畸形请求 {bad[:18]!r} 异常: {type(e).__name__}")

    # 未知路径
    try:
        op.open(f"http://127.0.0.1:{PORT}/nope", timeout=8)
        FAILS.append("未知路径应返回 404")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            FAILS.append(f"未知路径 → {e.code}（应为 404）")
finally:
    proc.terminate()
    time.sleep(0.4)
    out = proc.stdout.read() if proc.stdout else ""
    if "Traceback" in out:
        FAILS.append("服务端有未捕获异常:\n" + out[out.index("Traceback"):][:600])

if FAILS:
    print(f"✗ {len(FAILS)} 项失败：\n")
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("✓ 服务端 10 种输入 × 2 接口 + 畸形请求 + 404 全部正确")
