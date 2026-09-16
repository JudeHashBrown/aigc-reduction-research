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
    # ---- docx 出入口 ----
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "engine"))
    import base64
    from test_docx import make_docx

    doc = make_docx(["本文研究了该方法。研究表明，它具有重要的理论意义。",
                     "一句话总结：效果明显。当条件改变时，误差会上升。"], split_runs=True)
    b64doc = base64.b64encode(doc).decode()

    code, body = post("/api/docx/extract", {"file": b64doc})
    if code != 200 or "text" not in body:
        FAILS.append(f"docx 提取失败 {code}: {str(body)[:120]}")
    elif body["meta"]["n_paragraphs"] != 2:
        FAILS.append(f"docx 段落数错: {body['meta']}")
    else:
        code2, fixed = post("/api/autofix", {"text": body["text"]})
        if code2 != 200:
            FAILS.append(f"docx 文本走 autofix 失败 {code2}")
        else:
            code3, exp = post("/api/docx/export",
                              {"file": b64doc, "text": fixed["fixed_text"]})
            if code3 != 200 or "file" not in exp:
                FAILS.append(f"docx 导出失败 {code3}: {str(exp)[:160]}")
            else:
                try:
                    base64.b64decode(exp["file"], validate=True)
                except Exception as exc:
                    FAILS.append(f"导出的不是合法 base64: {exc}")

    # docx 畸形输入必须回 4xx，不能 500
    for name, payload in [("缺 file", {}),
                          ("file 非字符串", {"file": 123}),
                          ("非法 base64", {"file": "@@@not base64@@@"}),
                          ("不是 zip", {"file": base64.b64encode(b"hello").decode()}),
                          ("空 zip", {"file": base64.b64encode(
                              b"PK\x05\x06" + b"\x00" * 18).decode()})]:
        code, body = post("/api/docx/extract", payload)
        if not (400 <= code < 500) or "error" not in body:
            FAILS.append(f"docx 畸形输入「{name}」→ {code}（应为 4xx + error）")

    # 段落数对不上必须拒绝写回，而不是错位
    code, body = post("/api/docx/export", {"file": b64doc, "text": "只有一段。"})
    if not (400 <= code < 500):
        FAILS.append(f"docx 段落数不符 → {code}（必须拒绝，错位会毁掉整篇论文）")

    # ---- 零宽字符必须被清掉并如实告知 ----
    code, body = post("/api/diagnose", {"text": "研究\u200b表明该方法有效，具有重要的理论意\u200d义。"})
    if code != 200:
        FAILS.append(f"零宽字符输入 → {code}")
    else:
        ids = {f["rule_id"] for f in body["findings"]}
        if "S07" not in ids:
            FAILS.append(f"零宽字符仍让规则失效，命中 {ids}（必须先归一化再诊断）")
        if not any(n["level"] == "warn" for n in body.get("notices", [])):
            FAILS.append("清除了隐藏字符却没有告知用户")

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
print("✓ 服务端 10 输入 × 2 接口 + docx 出入口往返 + 5 种畸形 docx + 零宽归一化 + 404 全部正确")
