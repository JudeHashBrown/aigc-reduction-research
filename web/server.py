"""RightThesis 本地服务。账号模式依赖 requirements.txt。

    python3 web/server.py          # 默认 http://127.0.0.1:8765
    python3 web/server.py 9000     # 指定端口
"""
import json
import hashlib
import hmac
import ipaddress
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import webbrowser
from collections import deque
from contextlib import closing
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "engine"))
sys.path.insert(0, str(ROOT.parent / "probe"))

from diagnose import diagnose          # noqa: E402
import base64
import binascii
import threading
import time
from normalize import normalize_text, describe as describe_norm
import docx_io
import humanizer_bilingual
import pdf_io
from llm import Client                    # noqa: E402
from billing import BillingError, BillingStore, request_fingerprint  # noqa: E402
from payments import create_payment_provider                         # noqa: E402
from workspace_store import WorkspaceStore                           # noqa: E402
from admin_store import AdminStore                                   # noqa: E402
from traffic_store import TRACKED_ROUTES, TrafficError, TrafficStore  # noqa: E402
from privacy_store import PrivacyError, PrivacyStore                  # noqa: E402
from trial_session import (COOKIE_NAME, TrialSessionStore,
                           load_or_create_secret)                    # noqa: E402
from auth import (AUTH_COOKIE_NAME, AuthError, AuthStore, EmailDelivery,
                  GoogleOAuthClient, PASSWORD_MAX_LENGTH,
                  PASSWORD_MIN_LENGTH, normalize_email)             # noqa: E402

WEIGHTS = ROOT.parent / "engine" / "weights.json"
LOCAL_ENV = ROOT.parent / ".env"
APP_DIST = ROOT.parent / "platform-ui" / "dist" / "client"
LEGACY_INDEX = ROOT / "index.html"
LEGACY_APP = ROOT / "app.js"
_LOCAL_ENV_KEYS = {
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TEMPERATURE",
    "BILLING_DB", "PAYMENT_PROVIDER", "STRIPE_SECRET_KEY", "STRIPE_REFUND_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET", "STRIPE_LIVE_ENABLED",
    "TRIAL_MODE", "TRIAL_SESSION_SECRET",
    "TRIAL_SESSION_SECRET_FILE", "TRIAL_PUBLIC_ORIGIN",
    "TRIAL_CREDITS", "TRIAL_MAX_CHARS", "TRIAL_SESSION_DAYS",
    "TRIAL_BIND_HOST", "TRIAL_LAN_ORIGIN",
    "AUTH_MODE", "AUTH_SESSION_SECRET", "AUTH_SESSION_SECRET_FILE",
    "AUTH_SESSION_DAYS", "PUBLIC_ORIGIN", "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "AUTH_EMAIL_DELIVERY", "AUTH_EMAIL_FROM",
    "AUTH_SMTP_HOST", "AUTH_SMTP_PORT", "AUTH_SMTP_USERNAME",
    "AUTH_SMTP_PASSWORD", "AUTH_SMTP_SSL", "AUTH_SMTP_STARTTLS",
    "AUTH_SMTP_PROXY_URL",
    "ADMIN_EMAILS",
}


def _load_local_env(path=LOCAL_ENV):
    """Load only the model settings this local server understands.

    This deliberately avoids a general dotenv dependency and never logs
    values.  Existing process environment variables take precedence.
    """
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"无法读取本地模型配置：{exc}", flush=True)
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in _LOCAL_ENV_KEYS or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if value:
            os.environ[key] = value


_load_local_env()
# 硕士论文正文常在 3-8 万字。2 万的旧上限会把整篇论文截断一半，
# 而截断是静默发生的，用户拿到的报告只覆盖前半篇。
MAX_CHARS = 120000
MAX_BODY_BYTES = 64 * 1024 * 1024      # 请求体上限（docx 走 base64，约 1.37 倍膨胀）


_STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".wasm": "application/wasm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def _static_content_type(path: Path) -> str:
    """Return an explicit browser-safe MIME type for a frontend artifact."""
    explicit = _STATIC_CONTENT_TYPES.get(path.suffix.lower())
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _is_hashed_asset(path: Path) -> bool:
    """Recognize Vite's content-hash suffix without caching named assets forever."""
    stem = path.name.rsplit(".", 1)[0]
    suffix = stem.rsplit("-", 1)[-1]
    return (8 <= len(suffix) <= 32
            and re.fullmatch(r"[A-Za-z0-9_-]+", suffix) is not None
            and re.search(r"[A-Z0-9_]", suffix) is not None)


def _static_file(root: Path, url_path: str):
    """Resolve a URL path under ``root`` without allowing traversal/symlink escape.

    Returns ``(safe, file)``.  Missing files are safe and return ``None``;
    malformed or escaping paths return ``safe=False`` so callers never turn a
    traversal attempt into a successful SPA response.
    """
    try:
        decoded = unquote(url_path, errors="strict")
    except UnicodeError:
        return False, None
    if "\x00" in decoded or "\\" in decoded:
        return False, None
    relative = Path(decoded.lstrip("/"))
    if any(part == ".." for part in relative.parts):
        return False, None
    try:
        resolved_root = root.resolve()
        candidate = (resolved_root / relative).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return False, None
    return True, candidate if candidate.is_file() else None


def _billing_db_path() -> Path:
    configured = os.environ.get("BILLING_DB", "data/billing.sqlite3")
    path = Path(configured)
    return path if path.is_absolute() else ROOT.parent / path


ACCOUNT_ID = "local-demo"
BILLING = BillingStore(_billing_db_path())
WORKSPACES = WorkspaceStore(_billing_db_path())
ADMIN = AdminStore(_billing_db_path())
TRAFFIC = TrafficStore(_billing_db_path())
PRIVACY = PrivacyStore(_billing_db_path())
PAYMENTS = create_payment_provider(os.environ.get("PAYMENT_PROVIDER", "mock"), BILLING)
_TRAFFIC_RATE_LOCK = threading.Lock()
_TRAFFIC_RECENT = deque()


def _traffic_rate_allowed() -> bool:
    """Bound public analytics writes before they contend with the billing DB.

    Nginx also limits each client address. This process-wide backstop avoids
    treating untrusted forwarding headers as an identity or retaining IPs.
    """
    now = time.monotonic()
    with _TRAFFIC_RATE_LOCK:
        while _TRAFFIC_RECENT and _TRAFFIC_RECENT[0] <= now - 60:
            _TRAFFIC_RECENT.popleft()
        if len(_TRAFFIC_RECENT) >= 600:
            return False
        _TRAFFIC_RECENT.append(now)
        return True


def _health_status():
    """Readiness of the durable core; do not expose secrets or private data."""
    try:
        with closing(sqlite3.connect(f"file:{_billing_db_path()}?mode=ro", uri=True,
                                     timeout=2)) as db:
            result = db.execute("SELECT 1").fetchone()
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"accounts", "manuscripts", "rewrite_jobs", "orders", "ledger_entries", "traffic_daily"}
        if result != (1,) or not required <= tables:
            return 503, {"ok": False, "database": "unavailable"}
    except (OSError, sqlite3.Error):
        return 503, {"ok": False, "database": "unavailable"}
    if ACCOUNTS_MODE and PUBLIC_ORIGIN and urlparse(PUBLIC_ORIGIN).hostname not in {
        "127.0.0.1", "localhost", "::1"}:
        if not Client().configured or (PAYMENTS.name == "stripe" and not PAYMENTS.configured):
            return 503, {"ok": False, "service": "not_configured"}
    return 200, {"ok": True}


def _payment_status() -> dict:
    status = PAYMENTS.public_status()
    if PAYMENTS.name == "stripe" and not ACCOUNTS_MODE:
        return {**status, "checkout_enabled": False,
                "notice": "Stripe 支付仅对已验证并登录的账户开放。"}
    if TRIAL_MODE:
        return {**status, "checkout_enabled": False,
                "reason": "trial_checkout_disabled"}
    return status


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数") from exc
    if not minimum <= parsed <= maximum:
        raise RuntimeError(f"{name} 必须在 {minimum}-{maximum} 之间")
    return parsed


def _relative_data_path(name: str, default: str) -> Path:
    path = Path(os.environ.get(name, default))
    return path if path.is_absolute() else ROOT.parent / path


_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _is_private_v4(address) -> bool:
    return isinstance(address, ipaddress.IPv4Address) and any(
        address in network for network in _PRIVATE_V4)


def _canonical_origin(raw: str, scheme: str, name: str) -> str:
    if not raw:
        return ""
    try:
        parsed = urlparse(raw.rstrip("/"))
        # Accessing port also validates malformed/out-of-range values.
        parsed.port
    except ValueError as exc:
        raise RuntimeError(f"{name} 格式无效") from exc
    if (parsed.scheme != scheme or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.params or parsed.query
            or parsed.fragment or parsed.username or parsed.password):
        raise RuntimeError(f"{name} 必须是无路径的 {scheme.upper()} Origin")
    return f"{scheme}://{parsed.netloc.lower()}"


_legacy_trial_mode = _env_bool("TRIAL_MODE")
AUTH_MODE = os.environ.get(
    "AUTH_MODE", "trial" if _legacy_trial_mode else "local",
).strip().lower()
if AUTH_MODE not in {"local", "trial", "accounts"}:
    raise RuntimeError("AUTH_MODE 必须是 local、trial 或 accounts")
TRIAL_MODE = AUTH_MODE == "trial"
ACCOUNTS_MODE = AUTH_MODE == "accounts"
ADMIN_EMAILS = {normalize_email(value.strip()) for value in
                os.environ.get("ADMIN_EMAILS", "").split(",") if value.strip()}


def _admin_allowed(session: dict | None) -> bool:
    user = session.get("user") if session else None
    return bool(ACCOUNTS_MODE and session and session.get("authenticated") and isinstance(user, dict)
                and user.get("email") in ADMIN_EMAILS)
TRIAL_CREDITS = _env_int("TRIAL_CREDITS", 3000, 0, 10_000_000)
TRIAL_MAX_CHARS = _env_int("TRIAL_MAX_CHARS", 3000, 1, MAX_CHARS)
_trial_public_origin_raw = os.environ.get("TRIAL_PUBLIC_ORIGIN", "").strip()
TRIAL_PUBLIC_ORIGIN = (_canonical_origin(
    _trial_public_origin_raw, "https", "TRIAL_PUBLIC_ORIGIN")
    if TRIAL_MODE else "")


def _account_public_origin(raw: str) -> str:
    """Accept public HTTPS, plus exact localhost HTTP for OAuth development."""
    if not raw:
        return ""
    try:
        parsed = urlparse(raw.rstrip("/"))
        parsed.port
    except ValueError as exc:
        raise RuntimeError("PUBLIC_ORIGIN 格式无效") from exc
    local_http = (parsed.scheme == "http"
                  and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
    if ((parsed.scheme != "https" and not local_http) or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.params or parsed.query
            or parsed.fragment or parsed.username or parsed.password):
        raise RuntimeError("PUBLIC_ORIGIN 必须是无路径 HTTPS Origin，本地可使用 localhost HTTP")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


PUBLIC_ORIGIN = (_account_public_origin(
    os.environ.get("PUBLIC_ORIGIN", "").strip()) if ACCOUNTS_MODE else "")
GOOGLE_OAUTH_REDIRECT_URI = (os.environ.get(
    "GOOGLE_OAUTH_REDIRECT_URI", "",
).strip() if ACCOUNTS_MODE else "")
if GOOGLE_OAUTH_REDIRECT_URI:
    try:
        _google_redirect = urlparse(GOOGLE_OAUTH_REDIRECT_URI)
        _google_redirect.port
    except ValueError as exc:
        raise RuntimeError("GOOGLE_OAUTH_REDIRECT_URI 格式无效") from exc
    _google_redirect_origin = _account_public_origin(
        f"{_google_redirect.scheme}://{_google_redirect.netloc}")
    if (_google_redirect.path != "/api/auth/google/callback"
            or _google_redirect.params or _google_redirect.query
            or _google_redirect.fragment):
        raise RuntimeError(
            "GOOGLE_OAUTH_REDIRECT_URI 路径必须是 /api/auth/google/callback")
    if PUBLIC_ORIGIN and _google_redirect_origin != PUBLIC_ORIGIN:
        raise RuntimeError("GOOGLE_OAUTH_REDIRECT_URI 必须与 PUBLIC_ORIGIN 同源")
    if not PUBLIC_ORIGIN:
        # Keep the browser host, OAuth redirect host and cookie scope aligned
        # in local development (notably localhost versus 127.0.0.1).
        PUBLIC_ORIGIN = _google_redirect_origin
TRIAL_LAN_ORIGIN = _canonical_origin(
    os.environ.get("TRIAL_LAN_ORIGIN", "").strip(), "http",
    "TRIAL_LAN_ORIGIN")
TRIAL_BIND_HOST = os.environ.get("TRIAL_BIND_HOST", "127.0.0.1").strip()
try:
    _bind_ip = ipaddress.ip_address(TRIAL_BIND_HOST)
except ValueError as exc:
    raise RuntimeError("TRIAL_BIND_HOST 必须是 IPv4 字面量") from exc
if not isinstance(_bind_ip, ipaddress.IPv4Address):
    raise RuntimeError("TRIAL_BIND_HOST 目前只支持 IPv4")
_bind_is_non_loopback = not _bind_ip.is_loopback
if _bind_is_non_loopback:
    if not TRIAL_MODE:
        raise RuntimeError("非回环监听仅允许 TRIAL_MODE=1")
    if not (_bind_ip == ipaddress.ip_address("0.0.0.0") or _is_private_v4(_bind_ip)):
        raise RuntimeError("TRIAL_BIND_HOST 只允许私有 IPv4 或 0.0.0.0")
    if not TRIAL_LAN_ORIGIN:
        raise RuntimeError("非回环监听必须配置 TRIAL_LAN_ORIGIN")
if TRIAL_LAN_ORIGIN:
    if not (TRIAL_MODE and _bind_is_non_loopback):
        raise RuntimeError("TRIAL_LAN_ORIGIN 仅可用于匿名试用的非回环监听")
    try:
        _lan_ip = ipaddress.ip_address(urlparse(TRIAL_LAN_ORIGIN).hostname or "")
    except ValueError as exc:
        raise RuntimeError("TRIAL_LAN_ORIGIN 主机必须是私有 IPv4 字面量") from exc
    if not _is_private_v4(_lan_ip):
        raise RuntimeError("TRIAL_LAN_ORIGIN 主机必须是私有 IPv4")
    if _bind_ip != ipaddress.ip_address("0.0.0.0") and _lan_ip != _bind_ip:
        raise RuntimeError("TRIAL_LAN_ORIGIN 主机必须与 TRIAL_BIND_HOST 一致")
TRIAL_SESSIONS = None
if TRIAL_MODE:
    _secret = load_or_create_secret(
        _relative_data_path("TRIAL_SESSION_SECRET_FILE", "data/trial_session_secret"),
        os.environ.get("TRIAL_SESSION_SECRET"),
    )
    TRIAL_SESSIONS = TrialSessionStore(
        secret=_secret,
        session_seconds=_env_int("TRIAL_SESSION_DAYS", 7, 1, 90) * 86400,
    )

AUTH = None
EMAIL_DELIVERY = None
GOOGLE_OAUTH = None
if ACCOUNTS_MODE:
    _auth_secret = load_or_create_secret(
        _relative_data_path("AUTH_SESSION_SECRET_FILE", "data/auth_session_secret"),
        os.environ.get("AUTH_SESSION_SECRET"),
    )
    AUTH = AuthStore(
        _billing_db_path(), secret=_auth_secret,
        session_seconds=_env_int("AUTH_SESSION_DAYS", 7, 1, 90) * 86400,
    )
    EMAIL_DELIVERY = EmailDelivery.from_env()
    GOOGLE_OAUTH = GoogleOAuthClient.from_env()
    if EMAIL_DELIVERY.mode == "console" and PUBLIC_ORIGIN:
        _public_host = urlparse(PUBLIC_ORIGIN).hostname
        if _public_host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(
                "公网 accounts 模式不能使用 AUTH_EMAIL_DELIVERY=console")


# Jobs are durable: a refresh can resume polling and completed results survive
# process restarts. An interrupted in-flight call cannot safely be resumed.
MAX_ACTIVE_JOBS = 2


def _stable_job_id(account_id, request_id):
    raw = (account_id + "\0" + request_id).encode("utf-8")
    return "job_" + hashlib.sha256(raw).hexdigest()[:24]


def _new_job(account_id, request_id, fingerprint, manuscript_id=None, request=None):
    jid = _stable_job_id(account_id, request_id)
    claim, _ = WORKSPACES.claim_job(account_id, request_id, fingerprint, jid,
                                    MAX_ACTIVE_JOBS, manuscript_id, request)
    return (None if claim == "busy" else jid), claim


def _job_set(jid, **kw):
    WORKSPACES.update_job(jid, **kw)


def _not_charged_review_billing(jid):
    return {"job_id": jid, "status": "not_charged", "charged": 0,
            "released": 0, "llm_requests": 0, "input_tokens": 0,
            "output_tokens": 0}


def _run_queued_job(job):
    jid = job["id"]
    request = job.get("request") or {}
    text = request.get("text")
    strength = request.get("strength")
    review_target = request.get("review_target")
    client = None
    try:
        if not isinstance(text, str) or strength not in {"conservative", "balanced", "deep"}:
            raise ValueError("排队任务缺少可恢复的正文或策略")
        if review_target is not None:
            _job_set(jid, phase="checking", done=0, total=1)
            result = humanizer_bilingual.edit_review_finding(text, review_target)
            result["strength"] = strength
            result["notices"] = request.get("notices") or []
            result["model_usage"] = {"requests": 0, "input_tokens": 0,
                                     "output_tokens": 0, "total_tokens": 0}
            billing_result = _not_charged_review_billing(jid)
            result["billing"] = billing_result
            _job_set(jid, state="done", phase="complete", done=1, total=1,
                     result=result, billing=billing_result)
            return
        client = Client()
        if not client.configured:
            raise RuntimeError("平台改写服务暂不可用")
        _job_set(jid, phase="locating")
        result = humanizer_bilingual.humanize(
            text, client, n_candidates={"conservative": 1, "balanced": 2, "deep": 3}[strength],
            progress=lambda d, t: _job_set(jid, done=d, total=t, phase="rewriting"),
            auto_english=True, stage=lambda phase: _job_set(jid, phase=phase))
        result["strength"] = strength
        result["notices"] = request.get("notices") or []
        result["model_usage"] = client.usage_summary()
        _job_set(jid, phase="finalizing", result=result)
        billing_result = BILLING.finalize(
            jid, success=True, accepted=result.get("n_accepted", 0),
            usage=result["model_usage"])
        result["billing"] = billing_result
        _job_set(jid, state="done", phase="complete", result=result, billing=billing_result)
    except Exception as exc:  # noqa: BLE001
        import traceback
        print("\n[Humanizer 双语任务失败]\n" + traceback.format_exc(), flush=True)
        if review_target is not None:
            billing_result = _not_charged_review_billing(jid)
        else:
            try:
                billing_result = BILLING.finalize(
                    jid, success=False, accepted=0,
                    usage=client.usage_summary() if client else None)
            except Exception as billing_exc:  # noqa: BLE001
                print("\n[额度释放失败]\n" + str(billing_exc), flush=True)
                billing_result = {"status": "finalize_error", "error": str(billing_exc)}
        _job_set(jid, state="error", phase="error", error=str(exc), billing=billing_result)
    finally:
        _dispatch_jobs()


def _dispatch_jobs():
    while job := WORKSPACES.start_next_job(MAX_ACTIVE_JOBS):
        threading.Thread(target=_run_queued_job, args=(job,), daemon=True).start()


def _checked_manuscript(payload, creating=False):
    """Validate browser drafts before storing them beside billing data."""
    fields = ("name", "kind", "source", "current") if creating else ("current",)
    if any(not isinstance(payload.get(field), str) for field in fields):
        return None, "文稿字段类型无效"
    if creating and (payload["kind"] not in {"text", "txt", "docx", "pdf"}
                     or not payload["name"].strip() or len(payload["name"]) > 255
                     or not payload["source"].strip()
                     or len(payload["source"]) > MAX_CHARS):
        return None, "文稿类型、名称或原稿长度无效"
    if len(payload["current"]) > MAX_CHARS:
        return None, f"当前稿超过 {MAX_CHARS} 字上限"
    report = payload.get("report")
    notices = payload.get("notices", [])
    if report is not None and not isinstance(report, dict):
        return None, "report 必须是对象"
    if not isinstance(notices, list):
        return None, "notices 必须是列表"
    if (len(json.dumps(report, ensure_ascii=False))
            + len(json.dumps(notices, ensure_ascii=False))) > 8_000_000:
        return None, "文稿诊断结果过大"
    last_job_id = payload.get("last_job_id")
    if last_job_id is not None and (not isinstance(last_job_id, str)
                                    or not re.fullmatch(r"job_[0-9a-f]{24}", last_job_id)):
        return None, "任务编号无效"
    value = {field: payload[field] for field in fields}
    value.update(report=report, notices=notices, last_job_id=last_job_id)
    if creating:
        document = payload.get("document")
        if value["kind"] in {"docx", "pdf"}:
            if (not isinstance(document, dict)
                    or document.get("kind") != value["kind"]
                    or not isinstance(document.get("data"), str)):
                return None, "缺少原始文档文件"
            try:
                raw = base64.b64decode(document["data"], validate=True)
            except (ValueError, binascii.Error):
                return None, "原始文档编码无效"
            if not raw or len(raw) > 20 * 1024 * 1024:
                return None, "原始文档超过 20 MB 上限"
            if value["kind"] == "docx" and not raw.startswith(b"PK"):
                return None, "原始 DOCX 格式无效"
            if value["kind"] == "pdf" and not raw.startswith(b"%PDF-"):
                return None, "原始 PDF 格式无效"
            meta = document.get("meta") or {}
            if not isinstance(meta, dict) or len(json.dumps(meta, ensure_ascii=False)) > 1_000_000:
                return None, "文档元信息无效或过大"
            value["document"] = {
                "name": value["name"], "kind": value["kind"],
                "data": document["data"], "meta": meta,
            }
        elif document is not None:
            return None, "文本导入不应包含二进制文档"
        else:
            value["document"] = None
    return value, None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None,
              cache_control="no-store"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_file(self, path: Path, *, cache_control="no-cache", body=None):
        """Send a known-safe file while keeping HEAD metadata identical to GET."""
        try:
            data = path.read_bytes() if body is None else body
        except OSError:
            return self._send(404, json.dumps({"error": "not found"}))
        return self._send(200, data, _static_content_type(path),
                          cache_control=cache_control)

    def _redirect(self, location, code=303, headers=None):
        values = {"Location": location, **(headers or {})}
        return self._send(code, b"", "text/plain; charset=utf-8", headers=values)

    def _serve_frontend(self, path: str):
        """Serve the React build, or the legacy app when no build is available."""
        if ACCOUNTS_MODE and path in {"/legacy", "/legacy/", "/legacy/index.html", "/legacy/app.js"}:
            return self._redirect("/app")
        if path in {"/legacy", "/legacy/", "/legacy/index.html"}:
            try:
                # The old document uses an absolute /app.js reference.  Rewrite
                # that one URL so the legacy page remains isolated under its
                # advertised compatibility path.
                legacy_html = LEGACY_INDEX.read_bytes().replace(
                    b'<script src="/app.js"></script>',
                    b'<script src="/legacy/app.js"></script>',
                )
            except OSError:
                return self._send(404, json.dumps({"error": "not found"}))
            return self._send_file(LEGACY_INDEX, cache_control="no-store",
                                   body=legacy_html)
        if path == "/legacy/app.js":
            return self._send_file(LEGACY_APP, cache_control="no-cache")

        index = APP_DIST / "index.html"
        if not index.is_file():
            # Development/source-only checkouts still open the proven legacy
            # workbench rather than presenting a blank or partially built UI.
            if path in {"/", "/index.html"}:
                return self._send_file(LEGACY_INDEX, cache_control="no-store")
            if path == "/app.js":
                return self._send_file(LEGACY_APP, cache_control="no-cache")
            return self._send(404, json.dumps({"error": "not found"}))

        if path in {"/", "/index.html"}:
            return self._send_file(index, cache_control="no-store")

        # Google and other crawlers need the legal text in the initial HTML,
        # even when they do not execute the client-side React application.
        public_page = {
            "/legal/privacy": "privacy",
            "/legal/terms": "terms",
        }.get(path)
        if public_page:
            prerendered = APP_DIST / "legal" / public_page / "index.html"
            if prerendered.is_file():
                return self._send_file(prerendered, cache_control="no-store")

        safe, static_path = _static_file(APP_DIST, path)
        if not safe:
            return self._send(404, json.dumps({"error": "not found"}))
        if static_path is not None:
            cache_control = ("public, max-age=31536000, immutable"
                             if _is_hashed_asset(static_path) else "no-cache")
            return self._send_file(static_path, cache_control=cache_control)

        # Asset and extension-bearing misses are real 404s.  Returning HTML for
        # a missing JS/font request obscures deployment errors and triggers MIME
        # failures in the browser.  Clean application routes get the SPA shell.
        decoded = unquote(path)
        if decoded.startswith("/assets/") or Path(decoded).suffix:
            return self._send(404, json.dumps({"error": "not found"}))
        return self._send_file(index, cache_control="no-store")

    def _peer_is_loopback(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError):
            return False

    def _peer_is_private_or_loopback(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except (ValueError, IndexError):
            return False
        return address.is_loopback or _is_private_v4(address)

    def _effective_target(self):
        """Return (scheme, host, used_forwarding), or None if untrusted.

        Forwarding headers are honored only from a loopback reverse proxy.  In
        particular, X-Forwarded-For is never used for identity or rate limits.
        """
        raw_host = (self.headers.get("Host") or "").strip()
        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").strip()
        forwarded_host = (self.headers.get("X-Forwarded-Host") or "").strip()
        if forwarded_proto or forwarded_host:
            if not (TRIAL_MODE or ACCOUNTS_MODE) or not self._peer_is_loopback():
                return None
            if ("," in forwarded_proto or "," in forwarded_host
                    or forwarded_proto.lower() != "https"):
                return None
            return "https", (forwarded_host or raw_host).lower(), True
        # Tailscale Serve may preserve the public Host without adding
        # X-Forwarded-* headers.  Treat that exact host as HTTPS only because
        # the TCP peer is the local reverse proxy and the origin was explicitly
        # configured; no wildcard/suffix host matching is allowed.
        configured_public = PUBLIC_ORIGIN if ACCOUNTS_MODE else TRIAL_PUBLIC_ORIGIN
        public_host = (urlparse(configured_public).netloc.lower()
                       if configured_public else "")
        if (configured_public and public_host and self._peer_is_loopback()
                and raw_host.lower() == public_host):
            return urlparse(configured_public).scheme, raw_host.lower(), True
        lan_host = (urlparse(TRIAL_LAN_ORIGIN).netloc.lower()
                    if TRIAL_LAN_ORIGIN else "")
        if (TRIAL_MODE and lan_host
                and self._peer_is_private_or_loopback()
                and raw_host.lower() == lan_host):
            return "http", raw_host.lower(), False
        return "http", raw_host.lower(), False

    def _trusted_host(self):
        """Allow loopback directly or one explicitly configured HTTPS origin."""
        target = self._effective_target()
        if not target:
            return False
        scheme, raw, forwarded = target
        try:
            hostname = urlparse("//" + raw).hostname
        except ValueError:
            hostname = None
        if not forwarded:
            if hostname in {"127.0.0.1", "localhost", "::1"}:
                return self._peer_is_loopback()
            lan_host = (urlparse(TRIAL_LAN_ORIGIN).netloc.lower()
                        if TRIAL_LAN_ORIGIN else "")
            return bool(TRIAL_MODE and lan_host
                        and raw == lan_host
                        and self._peer_is_private_or_loopback())
        configured_public = PUBLIC_ORIGIN if ACCOUNTS_MODE else TRIAL_PUBLIC_ORIGIN
        return bool(configured_public and f"{scheme}://{raw}" == configured_public)

    def _is_lan_target(self):
        target = self._effective_target()
        return bool(target and TRIAL_LAN_ORIGIN
                    and f"{target[0]}://{target[1]}" == TRIAL_LAN_ORIGIN)

    def _origin_allowed(self, origin):
        target = self._effective_target()
        if not target:
            return False
        scheme, host, _ = target
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
        if (parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.params or parsed.query or parsed.fragment):
            return False
        return parsed.scheme.lower() == scheme and parsed.netloc.lower() == host

    def _cookie_value(self, name=None):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except CookieError:
            return None
        morsel = cookie.get(name or COOKIE_NAME)
        return morsel.value if morsel else None

    def _session_cookie(self, token):
        target = self._effective_target()
        secure = bool(target and target[0] == "https")
        value = (f"{COOKIE_NAME}={token}; Path=/; "
                 f"Max-Age={TRIAL_SESSIONS.session_seconds}; HttpOnly; SameSite=Strict")
        if secure:
            value += "; Secure"
        return value

    def _account_session_cookie(self, token):
        target = self._effective_target()
        secure = bool(target and target[0] == "https")
        value = (f"{AUTH_COOKIE_NAME}={token}; Path=/; "
                 f"Max-Age={AUTH.session_seconds}; HttpOnly; SameSite=Lax")
        if secure:
            value += "; Secure"
        return value

    def _clear_account_session_cookie(self):
        target = self._effective_target()
        secure = bool(target and target[0] == "https")
        value = (f"{AUTH_COOKIE_NAME}=; Path=/; Max-Age=0; "
                 "HttpOnly; SameSite=Lax")
        if secure:
            value += "; Secure"
        return value

    def _read_trial_session(self):
        if AUTH_MODE == "local":
            return {"account_id": ACCOUNT_ID,
                    "user": {"id": ACCOUNT_ID, "name": "本地用户",
                             "display_name": "本地用户", "label": "本地用户"},
                    "csrf_token": None}
        if ACCOUNTS_MODE:
            return AUTH.authenticate_session(self._cookie_value(AUTH_COOKIE_NAME))
        return TRIAL_SESSIONS.authenticate(self._cookie_value())

    def _create_guest_session(self):
        issued = TRIAL_SESSIONS.create_guest()
        session = {
            "account_id": issued["user"]["account_id"],
            "user": issued["user"],
            "csrf_token": issued["csrf_token"],
            "kind": "guest",
        }
        summary = BILLING.grant_trial(session["account_id"], TRIAL_CREDITS,
                                      TRIAL_MAX_CHARS)
        return session, issued["token"], summary

    def _require_trial_session(self):
        session = self._read_trial_session()
        if session is None:
            self._send(401, json.dumps({"error": "匿名会话已失效，请重新访问 /api/session",
                                        "authenticated": False}, ensure_ascii=False))
            return None
        BILLING.grant_trial(session["account_id"], TRIAL_CREDITS, TRIAL_MAX_CHARS)
        return session

    def _require_account_session(self, authenticated=True):
        session = self._read_trial_session()
        if session is None or (authenticated and not session.get("authenticated")):
            self._send(401, json.dumps({
                "error": "请先完成登录。",
                "code": "authentication_required",
                "authenticated": False,
            }, ensure_ascii=False))
            return None
        return session

    def _session_response(self, session):
        if ACCOUNTS_MODE:
            public_user = None
            if session and session.get("authenticated") and isinstance(session.get("user"), dict):
                public_user = dict(session["user"])
                public_user["role"] = "admin" if _admin_allowed(session) else "user"
            providers = {
                "email_password": True,
                "google": bool(GOOGLE_OAUTH and GOOGLE_OAUTH.configured),
            }
            response = {
                "auth_mode": "accounts",
                "trial_mode": False,
                "authenticated": bool(session and session.get("authenticated")),
                "user": public_user,
                "csrf_token": session.get("csrf_token") if session else None,
                "providers": providers,
                "auth": {
                    "mode": "accounts",
                    "providers": providers,
                    "password_policy": {
                        "min_length": PASSWORD_MIN_LENGTH,
                        "max_length": PASSWORD_MAX_LENGTH,
                    },
                    "email_verification_available": bool(
                        EMAIL_DELIVERY and EMAIL_DELIVERY.configured),
                    "email_delivery": EMAIL_DELIVERY.mode if EMAIL_DELIVERY else "disabled",
                },
            }
            if response["authenticated"]:
                response["billing"] = BILLING.summary(session["account_id"])
            return response
        if session is None:
            return {"trial_mode": TRIAL_MODE, "authenticated": False,
                    "user": None, "csrf_token": None}
        return {"trial_mode": TRIAL_MODE, "authenticated": True,
                "user": session["user"],
                "csrf_token": session.get("csrf_token")}

    def _csrf_allowed(self, session):
        if AUTH_MODE == "local":
            return True
        supplied = self.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf_token") or ""
        return bool(supplied and hmac.compare_digest(supplied, expected))

    def _send_auth_error(self, exc):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return self._send(exc.status, json.dumps({
            "error": str(exc), "code": exc.code,
        }, ensure_ascii=False), headers=headers)

    def _send_billing_error(self, exc):
        body = {"error": str(exc)}
        body.update(exc.details)
        return self._send(exc.status, json.dumps(body, ensure_ascii=False))

    def do_HEAD(self):
        """Support browser/CDN probes without changing API session semantics."""
        if not self._trusted_host():
            return self._send(403, json.dumps({"error": "请求主机或反向代理来源未被信任"},
                                              ensure_ascii=False))
        path = urlparse(self.path).path
        if path == "/health":
            code, status = _health_status()
            return self._send(code, json.dumps(status))
        if path == "/api" or path.startswith("/api/"):
            return self._send(405, json.dumps({"error": "method not allowed"}),
                              headers={"Allow": "GET, POST"})
        return self._serve_frontend(path)

    def do_GET(self):
        if not self._trusted_host():
            return self._send(403, json.dumps({"error": "请求主机或反向代理来源未被信任"},
                                              ensure_ascii=False))
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        if path == "/health":
            code, status = _health_status()
            return self._send(code, json.dumps(status))
        if path == "/api/session":
            session = self._read_trial_session()
            headers = None
            summary = None
            if session is None and ACCOUNTS_MODE:
                issued = AUTH.create_pre_auth()
                session = AUTH.authenticate_session(issued["token"])
                headers = {"Set-Cookie": self._account_session_cookie(issued["token"])}
            elif session is None and TRIAL_MODE:
                session, token, summary = self._create_guest_session()
                headers = {"Set-Cookie": self._session_cookie(token)}
            if session is not None and TRIAL_MODE:
                summary = summary or BILLING.grant_trial(
                    session["account_id"], TRIAL_CREDITS, TRIAL_MAX_CHARS)
            response = self._session_response(session)
            if summary is not None:
                response["billing"] = summary
            return self._send(200, json.dumps(response, ensure_ascii=False),
                              headers=headers)

        if ACCOUNTS_MODE and path == "/api/auth/google/start":
            if not GOOGLE_OAUTH.configured:
                return self._send_auth_error(AuthError(
                    "Google 登录尚未配置。", 503, "google_unavailable"))
            session = self._read_trial_session()
            headers = None
            token = self._cookie_value(AUTH_COOKIE_NAME)
            if session is None:
                issued = AUTH.create_pre_auth()
                token = issued["token"]
                session = AUTH.authenticate_session(token)
                headers = {"Set-Cookie": self._account_session_cookie(token)}
            if session.get("authenticated"):
                return self._redirect("/#/app", headers=headers)
            target = self._effective_target()
            redirect_uri = (GOOGLE_OAUTH_REDIRECT_URI
                            or f"{target[0]}://{target[1]}/api/auth/google/callback")
            return_to = parse_qs(parsed_path.query).get("return_to", ["/app"])[0]
            try:
                flow = AUTH.create_oauth_flow(token, return_to, redirect_uri)
                location = GOOGLE_OAUTH.authorization_url(flow)
            except AuthError as exc:
                return self._send_auth_error(exc)
            return self._redirect(location, code=302, headers=headers)

        if ACCOUNTS_MODE and path == "/api/auth/google/callback":
            query = parse_qs(parsed_path.query)
            token = self._cookie_value(AUTH_COOKIE_NAME)
            state = query.get("state", [""])[0]
            try:
                flow = AUTH.consume_oauth_flow(token, state)
                if query.get("error"):
                    raise AuthError("Google 登录已取消。", 400, "google_cancelled")
                identity = GOOGLE_OAUTH.exchange_and_verify(
                    query.get("code", [""])[0], flow,
                )
                logged_in = AUTH.rotate_authenticated(token, **identity)
            except AuthError as exc:
                location = "/#/auth?error=" + quote(exc.code, safe="")
                return self._redirect(location)
            location = "/#" + flow["return_to"]
            return self._redirect(location, headers={
                "Set-Cookie": self._account_session_cookie(logged_in["token"]),
            })

        session = self._read_trial_session()
        if TRIAL_MODE and path.startswith("/api/"):
            session = self._require_trial_session()
            if session is None:
                return
        elif ACCOUNTS_MODE and path.startswith("/api/") and path not in {
                "/api/config", "/api/billing/plans"}:
            session = self._require_account_session(authenticated=True)
            if session is None:
                return
        account_id = session["account_id"] if session else ACCOUNT_ID
        if path.startswith("/api/admin/"):
            if not _admin_allowed(session):
                return self._send(403, json.dumps({"error": "仅管理员可访问。"},
                                                  ensure_ascii=False))
            if path == "/api/admin/orders":
                params = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                try:
                    orders = BILLING.admin_orders(order_id=params.get("order_id", [""])[0])
                except BillingError as exc:
                    return self._send_billing_error(exc)
                return self._send(200, json.dumps({"orders": orders,
                                                  "refund_enabled": bool(getattr(PAYMENTS, "refund_enabled", False))},
                                                  ensure_ascii=False))
            if path == "/api/admin/users":
                params = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                query = params.get("q", [""])[0]
                try:
                    limit = int(params.get("limit", ["20"])[0])
                    offset = int(params.get("offset", ["0"])[0])
                except (TypeError, ValueError):
                    return self._send(400, json.dumps({"error": "分页参数无效。"}, ensure_ascii=False))
                if len(query) > 120 or not 1 <= limit <= 100 or not 0 <= offset <= 100_000:
                    return self._send(400, json.dumps({"error": "搜索或分页参数无效。"}, ensure_ascii=False))
                return self._send(200, json.dumps(
                    ADMIN.search_users(query, limit, offset), ensure_ascii=False))
            if path == "/api/admin/traffic":
                params = parse_qs(parsed_path.query, keep_blank_values=True)
                try:
                    days = int(params.get("days", ["30"])[0])
                    overview = TRAFFIC.overview(days)
                except (TypeError, ValueError, TrafficError):
                    return self._send(400, json.dumps({"error": "统计周期无效。"}, ensure_ascii=False))
                return self._send(200, json.dumps(overview, ensure_ascii=False))
            if path.startswith("/api/admin/users/"):
                user_id = unquote(path.removeprefix("/api/admin/users/"))
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id):
                    return self._send(400, json.dumps({"error": "账户编号无效。"}, ensure_ascii=False))
                detail = ADMIN.user_detail(user_id)
                if detail is None:
                    return self._send(404, json.dumps({"error": "账户不存在。"}, ensure_ascii=False))
                return self._send(200, json.dumps({"user": detail}, ensure_ascii=False))
            if path == "/api/admin/jobs":
                return self._send(200, json.dumps({"jobs": ADMIN.jobs()}, ensure_ascii=False))
            if path == "/api/admin/plans":
                return self._send(200, json.dumps({"plans": BILLING.public_catalog()}, ensure_ascii=False))
            if path == "/api/admin/economics":
                return self._send(200, json.dumps(ADMIN.economics(), ensure_ascii=False))
            if path == "/api/admin/service":
                return self._send(200, json.dumps(ADMIN.service(), ensure_ascii=False))
            if path == "/api/admin/privacy-requests":
                return self._send(200, json.dumps(
                    {"requests": PRIVACY.pending_requests()}, ensure_ascii=False))
            return self._send(404, json.dumps({"error": "not found"}))
        if path.startswith("/api/job/"):
            jid = path.rsplit("/", 1)[-1]
            j = WORKSPACES.get_job(account_id, jid)
            if not j:
                return self._send(404, json.dumps({"error": "任务不存在"},
                                                  ensure_ascii=False))
            out = {"state": j["state"], "phase": j.get("phase", "preparing"),
                   "done": j["done"], "total": j["total"],
                   "elapsed": round(time.time() - j["t0"], 1)}
            if j.get("billing") is not None:
                out["billing"] = j["billing"]
            if j["state"] == "done":
                out["result"] = j["result"]
            if j["state"] == "error":
                out["error"] = j["error"]
            return self._send(200, json.dumps(out, ensure_ascii=False))
        elif path == "/api/jobs":
            return self._send(200, json.dumps({
                "jobs": WORKSPACES.list_jobs(account_id),
            }, ensure_ascii=False))
        elif ACCOUNTS_MODE and path == "/api/account/data-export":
            try:
                exported = PRIVACY.export(account_id)
            except PrivacyError as exc:
                return self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False))
            return self._send(200, json.dumps(exported, ensure_ascii=False),
                              headers={"Content-Disposition":
                                       'attachment; filename="rightthesis-account-data.json"'})
        elif ACCOUNTS_MODE and path == "/api/account/privacy-request":
            return self._send(200, json.dumps({
                "request": PRIVACY.current_request(account_id),
            }, ensure_ascii=False))
        elif path == "/api/documents":
            return self._send(200, json.dumps({
                "documents": WORKSPACES.list_manuscripts(account_id),
            }, ensure_ascii=False))
        elif path.startswith("/api/documents/") and "/versions" in path:
            parts = path.split("/")
            if (len(parts) not in {5, 6} or parts[:3] != ["", "api", "documents"]
                    or parts[4] != "versions"):
                return self._send(404, json.dumps({"error": "not found"}))
            manuscript_id = parts[3]
            if not WORKSPACES.get_manuscript(account_id, manuscript_id):
                return self._send(404, json.dumps({"error": "文稿不存在"}, ensure_ascii=False))
            if len(parts) == 5:
                return self._send(200, json.dumps({
                    "versions": WORKSPACES.list_versions(account_id, manuscript_id),
                }, ensure_ascii=False))
            if not parts[5].isdecimal() or int(parts[5]) < 1:
                return self._send(404, json.dumps({"error": "版本不存在"}, ensure_ascii=False))
            version = WORKSPACES.get_version(account_id, manuscript_id, int(parts[5]))
            return self._send(200 if version else 404, json.dumps(
                {"version": version} if version else {"error": "版本不存在"},
                ensure_ascii=False))
        elif path.startswith("/api/documents/"):
            manuscript_id = path.rsplit("/", 1)[-1]
            manuscript = WORKSPACES.get_manuscript(account_id, manuscript_id)
            if not manuscript:
                return self._send(404, json.dumps({"error": "文稿不存在"},
                                                  ensure_ascii=False))
            return self._send(200, json.dumps({"document": manuscript},
                                              ensure_ascii=False))
        elif path == "/api/billing/plans":
            return self._send(200, json.dumps({
                "plans": BILLING.public_catalog(),
                "payment": _payment_status(),
            }, ensure_ascii=False))
        elif path == "/api/billing/summary":
            summary = BILLING.summary(account_id)
            summary["payment"] = _payment_status()
            return self._send(200, json.dumps(summary, ensure_ascii=False))
        elif path == "/api/billing/ledger":
            raw_limit = parse_qs(parsed_path.query).get("limit", ["30"])[0]
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                return self._send(400, json.dumps({"error": "limit 必须是整数"},
                                                  ensure_ascii=False))
            return self._send(200, json.dumps({
                "entries": BILLING.ledger(account_id, limit=limit),
            }, ensure_ascii=False))
        elif path == "/api/billing/orders":
            return self._send(200, json.dumps({
                "orders": BILLING.orders(account_id),
            }, ensure_ascii=False))
        elif path.startswith("/api/billing/orders/"):
            order_id = path.rsplit("/", 1)[-1]
            order = BILLING.order(account_id, order_id)
            if not order:
                return self._send(404, json.dumps({"error": "订单不存在"},
                                                  ensure_ascii=False))
            reconcile = getattr(PAYMENTS, "reconcile_order", None)
            if order["status"] in {"pending", "expired"} and callable(reconcile):
                try:
                    reconcile(account_id, order_id)
                    order = BILLING.order(account_id, order_id)
                except BillingError as exc:
                    # A transient Stripe read failure must not invent a paid
                    # state or hide the account-owned order from the buyer.
                    print(f"[Stripe 订单核对待重试] {order_id}: {exc}", flush=True)
            return self._send(200, json.dumps({"order": order}, ensure_ascii=False))
        elif path == "/api/config":
            c = Client()
            local_mode = not (ACCOUNTS_MODE and PUBLIC_ORIGIN
                              and urlparse(PUBLIC_ORIGIN).hostname not in
                              {"127.0.0.1", "localhost", "::1"})
            self._send(200, json.dumps({
                "llm_configured": c.configured,
                "llm_model": c.model if c.configured else None,
                "calibrated": WEIGHTS.exists(),
                "product_version": "0.2-local" if local_mode else "0.2",
                "policy": "Humanizer 中英双语",
                "supported_languages": ["zh", "en"],
                "checks": {"zh": 31, "en": 13},
                "local_mode": local_mode,
                "trial_mode": TRIAL_MODE,
                "auth_mode": AUTH_MODE,
                "auth_providers": ({
                    "email_password": True,
                    "google": bool(GOOGLE_OAUTH and GOOGLE_OAUTH.configured),
                } if ACCOUNTS_MODE else {}),
                "admin_read_only_configured": bool(ADMIN_EMAILS),
                "payment": _payment_status(),
            }, ensure_ascii=False))
        elif path == "/api" or path.startswith("/api/"):
            self._send(404, json.dumps({"error": "not found"}))
        else:
            self._serve_frontend(path)

    def do_POST(self):
        if not self._trusted_host():
            return self._send(403, json.dumps({"error": "请求主机或反向代理来源未被信任"},
                                              ensure_ascii=False))
        if urlparse(self.path).path == "/api/billing/stripe/webhook":
            return self._stripe_webhook()
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return self._send(415, json.dumps({"error": "只接受 application/json 请求"},
                                              ensure_ascii=False))
        origin = self.headers.get("Origin")
        if (self._is_lan_target() or ACCOUNTS_MODE) and not origin:
            return self._send(403, json.dumps({"error": "写请求必须携带精确 Origin"},
                                              ensure_ascii=False))
        if origin and not self._origin_allowed(origin):
            return self._send(403, json.dumps({"error": "拒绝跨站请求"},
                                              ensure_ascii=False))
        try:
            self._handle_post()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print("\n[请求处理失败]\n" + tb, flush=True)   # 控制台留痕，便于排查
            try:
                body = {"error": "服务端处理失败，详见终端输出"}
                if AUTH_MODE == "local":
                    body["detail"] = tb.strip().splitlines()[-1]
                self._send(500, json.dumps(body, ensure_ascii=False))
            except Exception:
                pass

    def _stripe_webhook(self):
        """Stripe-to-server callback: no browser cookie/Origin, only raw-body signature."""
        if not (ACCOUNTS_MODE and PAYMENTS.name == "stripe" and PAYMENTS.configured):
            return self._send(404, json.dumps({"error": "not found"}))
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length)
        except (TypeError, ValueError, OverflowError):
            return self._send(400, json.dumps({"error": "无效的请求长度"}, ensure_ascii=False))
        if length < 1 or length > 1024 * 1024:
            return self._send(413, json.dumps({"error": "回调体超出限制"}, ensure_ascii=False))
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self._send(415, json.dumps({"error": "回调类型无效"}, ensure_ascii=False))
        raw = self.rfile.read(length)
        if len(raw) != length:
            return self._send(400, json.dumps({"error": "回调体不完整"}, ensure_ascii=False))
        try:
            outcome = PAYMENTS.webhook(raw, self.headers.get("Stripe-Signature", ""))
        except BillingError as exc:
            return self._send_billing_error(exc)
        except Exception:
            return self._send(500, json.dumps({"error": "回调处理失败"}, ensure_ascii=False))
        return self._send(200, json.dumps({"ok": True, **outcome}, ensure_ascii=False))

    def _handle_post(self):
        path = urlparse(self.path).path
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return self._send(411, json.dumps({"error": "缺少 Content-Length"},
                                              ensure_ascii=False))
        try:
            n = int(raw_length)
        except (TypeError, ValueError, OverflowError):
            return self._send(400, json.dumps({"error": "Content-Length 格式无效"},
                                              ensure_ascii=False))
        if n < 0:
            return self._send(400, json.dumps({"error": "Content-Length 不能为负数"},
                                              ensure_ascii=False))
        if n > MAX_BODY_BYTES:
            return self._send(413, json.dumps({"error": "请求体过大"}, ensure_ascii=False))
        if path == "/api/traffic/page-view" and n > 128:
            return self._send(413, json.dumps({"error": "访问事件过大"}, ensure_ascii=False))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send(400, json.dumps({"error": "请求体不是合法 JSON"},
                                              ensure_ascii=False))
        # 类型必须校验：传 [] 或 {"text": 123} 都会在下面炸成 500，
        # 而那是客户端错误，应该回 400。
        if not isinstance(payload, dict):
            return self._send(400, json.dumps({"error": "请求体必须是 JSON 对象"},
                                              ensure_ascii=False))
        if path == "/api/traffic/page-view":
            if not ACCOUNTS_MODE:
                return self._send(404, json.dumps({"error": "not found"}))
            if set(payload) != {"path"}:
                return self._send(400, json.dumps({"error": "访问事件格式无效。"}, ensure_ascii=False))
            if not isinstance(payload["path"], str) or payload["path"] not in TRACKED_ROUTES:
                return self._send(400, json.dumps({"error": "页面路径无效。"}, ensure_ascii=False))
            try:
                if not _traffic_rate_allowed():
                    return self._send(429, json.dumps({"error": "访问事件过于频繁。"}, ensure_ascii=False),
                                      headers={"Retry-After": "60"})
                TRAFFIC.record(payload["path"])
            except TrafficError as exc:
                return self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False))
            return self._send(204, b"")
        if path in {"/api/session/login", "/api/session/logout"}:
            return self._send(410, json.dumps({
                "error": "手动会话入口已移除；试用模式会自动创建匿名会话。",
                "code": "session_operation_removed",
            }, ensure_ascii=False))

        session = self._read_trial_session()
        if TRIAL_MODE:
            session = self._require_trial_session()
            if session is None:
                return
            if not self._csrf_allowed(session):
                return self._send(403, json.dumps({"error": "CSRF 令牌无效"},
                                                  ensure_ascii=False))
        elif ACCOUNTS_MODE:
            session = self._require_account_session(authenticated=False)
            if session is None:
                return
            if not self._csrf_allowed(session):
                return self._send(403, json.dumps({"error": "CSRF 令牌无效"},
                                                  ensure_ascii=False))

            token = self._cookie_value(AUTH_COOKIE_NAME)
            if path in {"/api/auth/email/request-code", "/api/auth/email/verify-code"}:
                return self._send(404, json.dumps({"error": "not found"}))

            if path == "/api/auth/register":
                challenge = None
                try:
                    challenge = AUTH.begin_registration(
                        token, payload.get("email"), payload.get("password"),
                        payload.get("display_name", ""),
                    )
                    EMAIL_DELIVERY.send_code(
                        challenge["email"], challenge["code"],
                        purpose="register",
                        expires_minutes=challenge["expires_in"] // 60,
                        wait_for_delivery=True,
                    )
                except AuthError as exc:
                    if challenge:
                        AUTH.invalidate_email_challenge(challenge["challenge_id"])
                    return self._send_auth_error(exc)
                return self._send(202, json.dumps({
                    "ok": True,
                    "message": "注册验证码已发送。",
                    "challenge_id": challenge["challenge_id"],
                    "expires_in": challenge["expires_in"],
                    "resend_after": challenge["resend_after"],
                }, ensure_ascii=False))

            if path == "/api/auth/register/verify":
                try:
                    logged_in = AUTH.verify_registration(
                        token, payload.get("challenge_id"), payload.get("code"),
                    )
                except AuthError as exc:
                    return self._send_auth_error(exc)
                response = self._session_response(logged_in)
                return self._send(200, json.dumps(response, ensure_ascii=False), headers={
                    "Set-Cookie": self._account_session_cookie(logged_in["token"]),
                })

            if path == "/api/auth/register/resend":
                challenge = None
                try:
                    challenge = AUTH.resend_registration(
                        token, payload.get("challenge_id"),
                    )
                    EMAIL_DELIVERY.send_code(
                        challenge["email"], challenge["code"],
                        purpose="register",
                        expires_minutes=challenge["expires_in"] // 60,
                        wait_for_delivery=True,
                    )
                except AuthError as exc:
                    if challenge:
                        AUTH.invalidate_email_challenge(challenge["challenge_id"])
                    return self._send_auth_error(exc)
                return self._send(202, json.dumps({
                    "ok": True,
                    "message": "新的注册验证码已发送。",
                    "challenge_id": challenge["challenge_id"],
                    "expires_in": challenge["expires_in"],
                    "resend_after": challenge["resend_after"],
                }, ensure_ascii=False))

            if path == "/api/auth/login":
                try:
                    logged_in = AUTH.login_password(
                        token, payload.get("email"), payload.get("password"),
                    )
                except AuthError as exc:
                    return self._send_auth_error(exc)
                return self._send(200, json.dumps(
                    self._session_response(logged_in), ensure_ascii=False,
                ), headers={
                    "Set-Cookie": self._account_session_cookie(logged_in["token"]),
                })

            if path == "/api/auth/password/forgot":
                challenge = None
                try:
                    challenge = AUTH.begin_password_reset(
                        token, payload.get("email"),
                    )
                    # Known and unknown mailboxes take the same bounded queue
                    # path.  Unknown addresses enqueue a no-op task so SMTP
                    # latency cannot disclose whether an account exists.
                    EMAIL_DELIVERY.send_code(
                        challenge["email"], challenge["code"],
                        purpose="password_reset",
                        expires_minutes=challenge["expires_in"] // 60,
                        deliver=challenge["delivery_required"],
                    )
                except AuthError as exc:
                    # Account existence, invalid mailbox syntax and delivery
                    # availability are deliberately not reflected in this
                    # response.  Cooldowns still include Retry-After so the UI
                    # can avoid hammering the endpoint.
                    if challenge and exc.code in {
                            "email_delivery_failed", "email_login_unavailable",
                            "email_delivery_busy"}:
                        AUTH.invalidate_email_challenge(challenge["challenge_id"])
                    if exc.code in {"email_code_cooldown", "email_rate_limited"}:
                        return self._send(202, json.dumps({
                            "ok": True,
                            "message": "如果该邮箱已注册，重置验证码将发送到邮箱。",
                            "retry_after": exc.retry_after,
                        }, ensure_ascii=False))
                    challenge = None
                return self._send(202, json.dumps({
                    "ok": True,
                    "message": "如果该邮箱已注册，重置验证码将发送到邮箱。",
                    "challenge_id": (challenge["challenge_id"] if challenge
                                     else "emc_" + secrets.token_urlsafe(18)),
                    "expires_in": challenge["expires_in"] if challenge else 600,
                    "resend_after": challenge["resend_after"] if challenge else 60,
                }, ensure_ascii=False))

            if path == "/api/auth/password/reset":
                try:
                    logged_in = AUTH.reset_password(
                        token, payload.get("challenge_id"), payload.get("code"),
                        payload.get("new_password"),
                    )
                except AuthError as exc:
                    return self._send_auth_error(exc)
                return self._send(200, json.dumps(
                    self._session_response(logged_in), ensure_ascii=False,
                ), headers={
                    "Set-Cookie": self._account_session_cookie(logged_in["token"]),
                })

            if path == "/api/auth/logout":
                AUTH.revoke_session(token)
                return self._send(200, json.dumps({
                    "auth_mode": "accounts",
                    "trial_mode": False,
                    "authenticated": False,
                    "user": None,
                    "csrf_token": None,
                }, ensure_ascii=False), headers={
                    "Set-Cookie": self._clear_account_session_cookie(),
                })

            if not session.get("authenticated"):
                return self._send(401, json.dumps({
                    "error": "请先完成登录。",
                    "code": "authentication_required",
                    "authenticated": False,
                }, ensure_ascii=False))
        account_id = session["account_id"] if session else ACCOUNT_ID
        if path.startswith("/api/admin/"):
            if not _admin_allowed(session):
                return self._send(403, json.dumps({"error": "仅管理员可访问。"},
                                                  ensure_ascii=False))
            grant_match = re.fullmatch(r"/api/admin/users/([A-Za-z0-9_-]{1,128})/credits", path)
            if grant_match:
                target_account_id = grant_match.group(1)
                try:
                    grant = BILLING.grant_admin_credit(
                        account_id, target_account_id, payload.get("confirm_email"),
                        payload.get("credits"), payload.get("valid_days"),
                        payload.get("reason"), payload.get("request_id"),
                    )
                except BillingError as exc:
                    return self._send_billing_error(exc)
                return self._send(200 if grant["reused"] else 201, json.dumps({
                    "grant": grant, "user": ADMIN.user_detail(target_account_id),
                }, ensure_ascii=False))
            refund_match = re.fullmatch(r"/api/admin/orders/(ord_[0-9a-f]{32})/refund", path)
            if not refund_match:
                return self._send(404, json.dumps({"error": "not found"}))
            order_id = refund_match.group(1)
            if payload.get("confirm_order_id") != order_id:
                return self._send(400, json.dumps({"error": "请再次确认订单号。"},
                                                  ensure_ascii=False))
            try:
                if PAYMENTS.name != "stripe" or not getattr(PAYMENTS, "refund_enabled", False):
                    raise BillingError("管理员退款尚未配置独立的 Stripe 退款密钥", 503)
                attempt = PAYMENTS.issue_admin_refund(
                    order_id, account_id, payload.get("amount_fen"),
                    payload.get("reason"), payload.get("note"),
                    payload.get("attempt_id"))
            except BillingError as exc:
                return self._send_billing_error(exc)
            return self._send(202, json.dumps({"attempt": {
                "id": attempt["id"], "order_id": attempt["order_id"],
                "amount_fen": attempt["amount_fen"], "status": attempt["status"],
                "stripe_refund_id": attempt["stripe_refund_id"],
                "reused": bool(attempt.get("reused")),
            }}, ensure_ascii=False))
        if ACCOUNTS_MODE and path == "/api/account/delete-request":
            try:
                request = PRIVACY.request_deletion(
                    account_id, payload.get("confirm_email", ""))
            except PrivacyError as exc:
                return self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False))
            return self._send(202, json.dumps({"request": request}, ensure_ascii=False))
        if ACCOUNTS_MODE and path == "/api/account/delete-request/cancel":
            request = PRIVACY.cancel_deletion(account_id)
            return self._send(200, json.dumps({"request": request}, ensure_ascii=False))
        if path == "/api/documents":
            value, error = _checked_manuscript(payload, creating=True)
            if error:
                return self._send(400, json.dumps({"error": error}, ensure_ascii=False))
            manuscript = WORKSPACES.create_manuscript(account_id, value)
            return self._send(201, json.dumps({"document": manuscript}, ensure_ascii=False))
        if path.startswith("/api/documents/") and path.endswith("/save"):
            manuscript_id = path.split("/")[-2]
            revision = payload.get("revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                return self._send(400, json.dumps({"error": "revision 无效"}, ensure_ascii=False))
            value, error = _checked_manuscript(payload)
            if error:
                return self._send(400, json.dumps({"error": error}, ensure_ascii=False))
            if value["last_job_id"] and not WORKSPACES.get_job(account_id, value["last_job_id"]):
                return self._send(400, json.dumps({"error": "任务不属于当前账户"}, ensure_ascii=False))
            status, manuscript = WORKSPACES.update_manuscript(
                account_id, manuscript_id, revision, value)
            if status != "saved":
                return self._send(409 if status == "conflict" else 404,
                                  json.dumps({"error": "文稿已在另一页面修改，请先保存本地副本并重新打开。"
                                              if status == "conflict" else "文稿不存在",
                                              "code": status}, ensure_ascii=False))
            return self._send(200, json.dumps({"document": manuscript}, ensure_ascii=False))
        if path == "/api/billing/checkout":
            if TRIAL_MODE:
                return self._send(403, json.dumps({
                    "error": "当前访问方式不支持购买。如需额度，请联系管理员。",
                    "code": "trial_checkout_disabled",
                }, ensure_ascii=False))
            product_id = payload.get("product_id")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(product_id, str):
                return self._send(400, json.dumps({"error": "product_id 必须是字符串"},
                                                  ensure_ascii=False))
            try:
                if PAYMENTS.name == "stripe" and not ACCOUNTS_MODE:
                    raise BillingError("Stripe 仅支持已登录账户购买", 403)
                target = self._effective_target()
                origin = f"{target[0]}://{target[1]}" if target else ""
                user = session.get("user") if ACCOUNTS_MODE else None
                customer_email = (user.get("email", "") if user and
                                  user.get("email_verified") else "")
                result = PAYMENTS.checkout(account_id, product_id,
                                           idempotency_key, origin=origin,
                                           customer_email=customer_email)
            except BillingError as exc:
                return self._send_billing_error(exc)
            return self._send(200, json.dumps(result, ensure_ascii=False))

        raw = payload.get("text")
        if raw is not None and not isinstance(raw, str):
            return self._send(400, json.dumps({"error": "text 字段必须是字符串"},
                                              ensure_ascii=False))
        # docx 接口不走文本路径，先分流
        if path.startswith("/api/docx/") or path.startswith("/api/pdf/"):
            return self._handle_doc(payload)

        # 归一化：零宽字符会让**全部规则失效**，必须在诊断之前清掉。
        # 清掉了什么要如实告诉用户——那本身就是有价值的信息。
        text, norm = normalize_text(raw or "")
        truncated = len(text) > MAX_CHARS
        if path == "/api/v1/rewrite-jobs" and truncated:
            return self._send(422, json.dumps({
                "error": f"文本超过 {MAX_CHARS} 字改写上限，请分章提交；本次未截断、未扣额度。",
                "max_chars": MAX_CHARS,
            }, ensure_ascii=False))
        text = text[:MAX_CHARS]
        if not text.strip():
            return self._send(400, json.dumps({"error": "文本为空"}, ensure_ascii=False))
        notices = describe_norm(norm)
        if truncated:
            notices.insert(0, {"level": "warn",
                               "text": f"文本超过 {MAX_CHARS} 字上限，只处理了前 {MAX_CHARS} 字。"})

        # ---- Humanizer bilingual local MVP API ---------------------------
        # Kept alongside the legacy endpoints during migration.  The v1 API
        # reports editing signals, never a fabricated detector percentage.
        if path == "/api/v1/analyze":
            r = humanizer_bilingual.analyze(text)
            r["notices"] = notices
            return self._send(200, json.dumps(r, ensure_ascii=False))

        if path == "/api/v1/autofix":
            r = humanizer_bilingual.autofix(text)
            r["notices"] = notices
            return self._send(200, json.dumps(r, ensure_ascii=False))

        if path == "/api/v1/rewrite-jobs":
            strength = payload.get("strength") or "conservative"
            if strength not in {"conservative", "balanced", "deep"}:
                return self._send(400, json.dumps({"error": "strength 参数无效"},
                                                  ensure_ascii=False))
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not re.fullmatch(
                    r"[A-Za-z0-9_-]{8,100}", request_id):
                return self._send(400, json.dumps({
                    "error": "request_id 必须是 8-100 位字母、数字、下划线或短横线。"
                }, ensure_ascii=False))
            manuscript_id = payload.get("manuscript_id")
            if manuscript_id is not None:
                if not isinstance(manuscript_id, str):
                    return self._send(400, json.dumps({"error": "manuscript_id 无效"},
                                                      ensure_ascii=False))
                manuscript = WORKSPACES.get_manuscript(account_id, manuscript_id)
                if not manuscript:
                    return self._send(404, json.dumps({"error": "文稿不存在"},
                                                      ensure_ascii=False))
                if manuscript["current"] != text:
                    return self._send(409, json.dumps({
                        "error": "当前稿尚未保存，请等待保存完成后再启动改写。"
                    }, ensure_ascii=False))
            review_target = payload.get("review_target")
            if review_target is not None:
                if not manuscript_id:
                    return self._send(400, json.dumps({
                        "error": "单项自动修改必须关联已保存的当前稿。",
                        "code": "review_target_requires_manuscript",
                    }, ensure_ascii=False))
                if (not isinstance(review_target, dict)
                        or review_target.get("pattern_id") != "EN-S01"
                        or type(review_target.get("start")) is not int
                        or type(review_target.get("end")) is not int
                        or not isinstance(review_target.get("matched"), str)):
                    return self._send(400, json.dumps({
                        "error": "review_target 仅支持有效的 EN-S01 诊断项。",
                        "code": "invalid_review_target",
                    }, ensure_ascii=False))
                finding = humanizer_bilingual.find_review_target(text, review_target)
                if finding is None:
                    return self._send(409, json.dumps({
                        "error": "诊断项与当前正文不一致，请重新分析后再试。",
                        "code": "stale_review_target",
                    }, ensure_ascii=False))
                review_target = {"pattern_id": "EN-S01", "start": finding["start"],
                                 "end": finding["end"], "matched": finding["matched"]}
                fingerprint = hashlib.sha256((
                    "review-target\0" + strength + "\0" + text + "\0" + json.dumps(
                        review_target, sort_keys=True, ensure_ascii=False)
                ).encode("utf-8")).hexdigest()
            else:
                client = Client()
                if not client.configured:
                    return self._send(400, json.dumps({
                        "error": "平台改写服务暂不可用，请联系管理员检查服务端模型配置。"
                    }, ensure_ascii=False))
                fingerprint = request_fingerprint(text, strength)
            jid, claim = _new_job(account_id, request_id, fingerprint, manuscript_id,
                                  {"text": text, "strength": strength, "notices": notices,
                                   **({"review_target": review_target}
                                      if review_target is not None else {})})
            if claim == "busy":
                return self._send(429, json.dumps({
                    "error": "当前排队任务已满，请等待已有任务完成后再提交。"
                }, ensure_ascii=False))
            if claim == "conflict":
                return self._send(409, json.dumps({
                    "error": "同一 request_id 不能用于不同文本或强度。"
                }, ensure_ascii=False))
            if claim == "reused":
                return self._send(200, json.dumps({
                    "job": jid, "reused": True,
                }, ensure_ascii=False))

            if review_target is not None:
                # A bounded, deterministic edit neither calls the model nor
                # reserves character credits.  A non-null billing marker lets
                # the durable queue dispatch and recover it normally.
                reservation = _not_charged_review_billing(jid)
                _job_set(jid, billing=reservation)
                if manuscript_id:
                    WORKSPACES.mark_last_job(account_id, manuscript_id, jid)
                _dispatch_jobs()
                return self._send(200, json.dumps({
                    "job": jid, "reused": False, "billing": reservation,
                }, ensure_ascii=False))

            try:
                reservation = BILLING.reserve(
                    account_id, jid, text, strength, fingerprint=fingerprint)
            except BillingError as exc:
                rejected = {"status": "rejected", **exc.details}
                _job_set(jid, state="error", error=str(exc), billing=rejected)
                return self._send_billing_error(exc)
            if reservation.get("reused"):
                _job_set(jid, state="error", billing=reservation,
                         error="该任务已有额度预占，但未找到可恢复的结果；请核对额度流水。")
                return self._send(409, json.dumps({
                    "error": "该任务已有额度预占；为避免重复消耗，未再次运行。请核对额度流水。",
                    "reservation_status": reservation.get("status"),
                }, ensure_ascii=False))
            _job_set(jid, billing=reservation)
            if manuscript_id:
                WORKSPACES.mark_last_job(account_id, manuscript_id, jid)
            _dispatch_jobs()
            return self._send(200, json.dumps({
                "job": jid, "reused": False, "billing": reservation,
            }, ensure_ascii=False))

        wp = str(WEIGHTS) if WEIGHTS.exists() else None
        if path == "/api/diagnose":
            r = diagnose(text, weights_path=wp)
            r["text"] = text
            r["calibrated"] = WEIGHTS.exists()
            r["notices"] = notices
            return self._send(200, json.dumps(r, ensure_ascii=False))

        if path == "/api/autofix":
            # Legacy response shape, but route the work through the same safe
            # bilingual product engine as v1 instead of the retired rule rewriter.
            result = humanizer_bilingual.autofix(text)
            fixed, log = result["text"], result["log"]
            before, after = result["before"], result["after"]
            return self._send(200, json.dumps({
                "fixed_text": fixed, "log": log,
                "before": before["summary"], "after": after["summary"],
                "after_full": after, "text": fixed, "notices": notices,
            }, ensure_ascii=False))

        if path == "/api/rewrite":
            return self._send(410, json.dumps({
                "error": "旧版改写接口已停用；请使用 /api/v1/rewrite-jobs。"
            }, ensure_ascii=False))

        self._send(404, json.dumps({"error": "not found"}))

    def _handle_doc(self, payload):
        """DOCX/PDF import/export; persisted manuscripts retain original bytes."""
        b64 = payload.get("file")
        if not isinstance(b64, str) or not b64:
            return self._send(400, json.dumps({"error": "缺少 file 字段（base64 编码的文档）"},
                                              ensure_ascii=False))
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception:
            return self._send(400, json.dumps({"error": "file 不是合法的 base64"},
                                              ensure_ascii=False))

        if self.path == "/api/pdf/extract":
            # PDF 只读：它存的是字形坐标而不是段落，没有可靠的回写路径。
            try:
                text, meta = pdf_io.extract(data)
            except pdf_io.PdfError as exc:
                return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))
            clean, norm = normalize_text(text)
            notices = pdf_io.notices(meta) + describe_norm(norm)
            if len(clean) > MAX_CHARS:
                notices.insert(0, {"level": "warn",
                                   "text": f"正文 {len(clean)} 字，超过 {MAX_CHARS} 字上限，"
                                           f"只诊断前 {MAX_CHARS} 字。"})
                clean = clean[:MAX_CHARS]
            return self._send(200, json.dumps({"text": clean, "meta": meta, "kind": "pdf",
                                               "notices": notices}, ensure_ascii=False))

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
            if meta.get("has_tracked_changes"):
                notices.append({"level": "warn",
                                "text": "检测到 Word 修订痕迹：已忽略删除内容并提取当前插入内容。"
                                        "为避免审阅状态混淆，建议先在 Word 中接受或拒绝修订后再处理。"})
            if len(clean) > MAX_CHARS:
                notices.insert(0, {"level": "warn",
                                   "text": f"正文 {len(clean)} 字，超过 {MAX_CHARS} 字上限。"})
            meta.pop("para_map", None)          # 下标由服务端在导出时重算，不外传
            return self._send(200, json.dumps({"text": clean, "meta": meta, "kind": "docx",
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


def _runtime_url(port: int) -> str:
    if TRIAL_LAN_ORIGIN:
        parsed = urlparse(TRIAL_LAN_ORIGIN)
        origin_port = parsed.port or 80
        if origin_port != port:
            raise RuntimeError(
                f"TRIAL_LAN_ORIGIN 端口 {origin_port} 与服务端口 {port} 不一致")
        return TRIAL_LAN_ORIGIN
    if ACCOUNTS_MODE and PUBLIC_ORIGIN:
        return PUBLIC_ORIGIN
    return f"http://{TRIAL_BIND_HOST}:{port}"


def _recover_interrupted_jobs():
    """Finish saved results, or release credit for work killed mid-generation."""
    for job in WORKSPACES.unreserved_jobs():
        # A crash may land between the queued claim and the reservation write.
        # Never dispatch or indefinitely count such a task against queue slots.
        if not (job.get("request") or {}).get("review_target"):
            try:
                BILLING.finalize(job["id"], success=False, accepted=0)
            except BillingError as exc:
                print(f"[排队任务预占恢复待核对] {job['id']}: {exc}", flush=True)
        WORKSPACES.update_job(job["id"], state="error", phase="error",
                              error="服务在任务排队时中断；请重新提交。")
    for job in WORKSPACES.running_jobs():
        owner_pid = job.get("owner_pid")
        if owner_pid and owner_pid != os.getpid():
            try:
                os.kill(owner_pid, 0)
            except ProcessLookupError:
                pass
            except PermissionError:
                continue
            else:
                continue
        result = job.get("result")
        if (job.get("request") or {}).get("review_target"):
            billing_result = _not_charged_review_billing(job["id"])
        else:
            try:
                billing_result = BILLING.finalize(
                    job["id"], success=bool(result),
                    accepted=int((result or {}).get("n_accepted") or 0),
                    usage=(result or {}).get("model_usage"))
            except BillingError as exc:
                billing_result = {"status": "recovery_error", "error": str(exc)}
        if result:
            result["billing"] = billing_result
            WORKSPACES.update_job(job["id"], state="done", phase="complete",
                                  result=result, billing=billing_result)
        else:
            WORKSPACES.update_job(
                job["id"], state="error", phase="error", billing=billing_result,
                error="服务在改写过程中中断；未生成可用结果，预占额度已尝试退回。")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    try:
        url = _runtime_url(port)
    except RuntimeError as e:
        print(f"配置无效：{e}", flush=True)
        sys.exit(2)
    try:
        srv = ThreadingHTTPServer((TRIAL_BIND_HOST, port), Handler)
    except OSError as e:
        print(f"无法在端口 {port} 启动：{e}")
        print(f"多半是端口被占用。换一个端口试试：python3 web/server.py {port + 1}")
        sys.exit(1)
    _recover_interrupted_jobs()
    _dispatch_jobs()
    print(f"诊断服务已启动 → {url}", flush=True)
    if ACCOUNTS_MODE:
        print("账号模式：邮箱密码（注册/重置需验证邮箱）"
              + (" + Google" if GOOGLE_OAUTH.configured else "；Google 尚未配置"),
              flush=True)
        print(f"邮件投递：{EMAIL_DELIVERY.mode}", flush=True)
    if TRIAL_LAN_ORIGIN:
        print(f"局域网开放内测 → {TRIAL_LAN_ORIGIN}", flush=True)
        print(f"监听地址：{TRIAL_BIND_HOST}:{port}（仅接受配置的精确 Host/Origin）",
              flush=True)
    print(f"权重：{'已标定 weights.json' if WEIGHTS.exists() else '临时权重（未经探测标定）'}")
    _c = Client()
    print(f"LLM ：{_c.model + ' 已就绪' if _c.configured else '未配置（只有规则层可用）'}"
          + ("" if _c.configured else "\n      设置 LLM_BASE_URL 与 LLM_API_KEY 后重启即可启用改写层"))
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
