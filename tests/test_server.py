"""服务端接口测试：确保任何输入都返回合法 JSON，不挂、不 500。"""
import json
import os
import subprocess
import sys
import tempfile
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
        # 同一个请求只发一次。旧写法分别取 status 和 body 时各 open 一次，
        # 若未来用在收费 LLM 接口会重复扣额度。
        with op.open(req, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"_raw": body[:200].decode("utf-8", "replace")}


billing_tmp = tempfile.TemporaryDirectory()
server_env = os.environ.copy()
server_env["AUTH_MODE"] = "local"
server_env["TRIAL_MODE"] = "0"
server_env["BILLING_DB"] = str(Path(billing_tmp.name) / "billing.sqlite3")
server_env["PAYMENT_PROVIDER"] = "mock"
# The S11 integration case below is fully deterministic and must never reach
# the network.  A configured, deliberately unreachable endpoint proves that a
# passing test did not depend on a developer's real key or provider.
server_env["LLM_BASE_URL"] = "http://127.0.0.1:1/v1"
server_env["LLM_API_KEY"] = "test-only-not-used"
server_env["LLM_MODEL"] = "test-deterministic-s11"
proc = subprocess.Popen([sys.executable, str(ROOT / "web/server.py"), str(PORT)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        env=server_env)
time.sleep(3)
try:
    for path in ["/", "/legacy", "/legacy/app.js", "/health", "/api/config",
                 "/api/billing/plans",
                 "/api/billing/summary", "/api/billing/ledger?limit=5"]:
        try:
            r = op.open(f"http://127.0.0.1:{PORT}{path}", timeout=8)
            if r.status != 200:
                FAILS.append(f"GET {path} → {r.status}")
        except Exception as e:
            FAILS.append(f"GET {path} 失败: {e}")

    # ---- 本地 mock 付费与服务端定价 ----
    code, checkout = post("/api/billing/checkout", {
        "product_id": "pack_3k",
        "idempotency_key": "server_checkout_001",
        # 这些攻击者控制的字段必须被忽略。
        "amount_fen": 1,
        "credits": 999999,
    })
    if code != 200:
        FAILS.append(f"mock checkout → {code}: {checkout}")
    else:
        if checkout.get("live") is not False or checkout.get("provider") != "mock":
            FAILS.append(f"mock checkout 未明确标识非真实支付: {checkout}")
        if checkout.get("summary", {}).get("balance") != 3800:
            FAILS.append("服务端未按自有产品表发放 3000 字")

    code2, repeated = post("/api/billing/checkout", {
        "product_id": "pack_3k",
        "idempotency_key": "server_checkout_001",
    })
    if code2 != 200 or repeated.get("reused") is not True:
        FAILS.append(f"mock checkout 幂等重试失败: {code2} {repeated}")
    elif repeated.get("summary", {}).get("balance") != 3800:
        FAILS.append("mock checkout 重试重复发放了额度")

    code3, conflict = post("/api/billing/checkout", {
        "product_id": "pack_10k",
        "idempotency_key": "server_checkout_001",
    })
    if code3 != 409 or "error" not in conflict:
        FAILS.append(f"同一幂等键换套餐 → {code3}（应为 409）")

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
        for api in ["/api/diagnose", "/api/autofix",
                    "/api/v1/analyze", "/api/v1/autofix"]:
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

    # ---- S11 + S01 同段：确定性改写、异步任务与计费结算 ----
    english_source = (
        "It was found that AI writing tools may improve editing efficiency. "
        "This study provides robust, comprehensive, and valuable insights."
    )
    english_expected = (
        "AI writing tools may improve editing efficiency. "
        "This study provides robust, comprehensive, and valuable insights."
    )
    code, started = post("/api/v1/rewrite-jobs", {
        "text": english_source,
        "strength": "conservative",
        "request_id": "server_s11_s01_0001",
    })
    if code != 200 or not started.get("job"):
        FAILS.append(f"S11+S01 改写任务启动失败: {code} {started}")
    else:
        job = None
        for _ in range(80):
            try:
                with op.open(
                        f"http://127.0.0.1:{PORT}/api/job/{started['job']}",
                        timeout=8) as response:
                    job = json.loads(response.read())
            except Exception as exc:
                FAILS.append(f"S11+S01 任务查询失败: {exc}")
                break
            if job.get("state") in {"done", "error"}:
                break
            time.sleep(0.05)
        if not job or job.get("state") != "done":
            FAILS.append(f"S11+S01 任务未完成: {job}")
        else:
            result = job.get("result") or {}
            billing = result.get("billing") or {}
            if result.get("text") != english_expected:
                FAILS.append("S11 确定性改写改动了被动壳以外的正文")
            if result.get("n_accepted") != 1 or result.get("n_chunks") != 1:
                FAILS.append(f"S11+S01 采纳计数错误: {result}")
            if billing.get("status") != "committed" or billing.get("llm_requests") != 0:
                FAILS.append(f"S11 确定性任务结算错误: {billing}")

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

    # 本地付费模型接口不得被普通网页跨站调用或 DNS rebinding 套取。
    security_cases = [
        ("非 JSON Content-Type", "/api/v1/analyze", {"Content-Type": "text/plain"}, 415),
        ("跨站 Origin", "/api/v1/analyze",
         {"Content-Type": "application/json", "Origin": "http://evil.example"}, 403),
        ("非回环 Host", "/api/v1/analyze",
         {"Content-Type": "application/json", "Host": "evil.example:8799"}, 403),
        ("已退役旧改写接口", "/api/rewrite", {"Content-Type": "application/json"}, 410),
    ]
    for name, path, headers, expected in security_cases:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}{path}",
            data='{"text":"测试"}'.encode(), headers=headers)
        try:
            op.open(req, timeout=10)
            FAILS.append(f"{name} 应返回 {expected}")
        except urllib.error.HTTPError as e:
            if e.code != expected:
                FAILS.append(f"{name} → {e.code}（应为 {expected}）")
        except Exception as e:
            FAILS.append(f"{name} 异常: {type(e).__name__}: {e}")

    # 未知 API 不得落入前端 SPA。
    try:
        op.open(f"http://127.0.0.1:{PORT}/api/nope", timeout=8)
        FAILS.append("未知 API 路径应返回 404")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            FAILS.append(f"未知 API 路径 → {e.code}（应为 404）")
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
    billing_tmp.cleanup()

if FAILS:
    print(f"✗ {len(FAILS)} 项失败：\n")
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("✓ 服务端输入/docx/安全 + mock 支付幂等与服务端定价全部正确")
