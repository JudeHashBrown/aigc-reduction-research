"""HTTP coverage for the built-frontend bridge and legacy compatibility path."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def request(opener, base, path, method="GET"):
    req = urllib.request.Request(base + path, method=method)
    try:
        with opener.open(req, timeout=5) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def run():
    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)
        os.environ.update({
            "AUTH_MODE": "local",
            "TRIAL_MODE": "0",
            "TRIAL_BIND_HOST": "127.0.0.1",
            "TRIAL_LAN_ORIGIN": "",
            "TRIAL_PUBLIC_ORIGIN": "",
            "BILLING_DB": str(folder / "billing.sqlite3"),
            "PAYMENT_PROVIDER": "mock",
            "BROWSER": "/usr/bin/true",
        })
        sys.path.insert(0, str(ROOT / "web"))
        import server  # noqa: E402

        dist = folder / "client"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        index = b"<!doctype html><title>RightThesis React</title><div id='root'></div>"
        (dist / "index.html").write_bytes(index)
        privacy = b"<!doctype html><title>Privacy</title><main>Privacy policy text</main>"
        terms = b"<!doctype html><title>Terms</title><main>Terms of service text</main>"
        (dist / "legal" / "privacy").mkdir(parents=True)
        (dist / "legal" / "terms").mkdir(parents=True)
        (dist / "legal" / "privacy" / "index.html").write_bytes(privacy)
        (dist / "legal" / "terms" / "index.html").write_bytes(terms)
        (assets / "index-AbCd1234.js").write_bytes(b"window.RIGHTTHESIS = true;")
        (assets / "index-EfGh5678.css").write_bytes(b"body{color:#111}")
        (assets / "brand.png").write_bytes(b"not-a-real-png")
        secret = folder / "secret.txt"
        secret.write_text("must never be served", encoding="utf-8")
        (assets / "leak.txt").symlink_to(secret)
        server.APP_DIST = dist

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            code, body, headers = request(opener, base, "/")
            assert code == 200 and body == index
            assert headers.get_content_type() == "text/html"
            assert headers["Cache-Control"] == "no-store"

            code, body, headers = request(opener, base, "/legal/privacy")
            assert code == 200 and body == privacy
            assert headers.get_content_type() == "text/html"
            assert headers["Cache-Control"] == "no-store"
            code, body, headers = request(opener, base, "/legal/terms")
            assert code == 200 and body == terms
            assert headers.get_content_type() == "text/html"

            code, body, headers = request(opener, base, "/workspace/document-1?tab=review")
            assert code == 200 and body == index
            assert headers.get_content_type() == "text/html"

            code, body, headers = request(
                opener, base, "/workspace/document-1", method="HEAD",
            )
            assert code == 200 and body == b""
            assert int(headers["Content-Length"]) == len(index)

            code, body, headers = request(opener, base, "/assets/index-AbCd1234.js")
            assert code == 200 and body == b"window.RIGHTTHESIS = true;"
            assert headers.get_content_type() == "text/javascript"
            assert headers["Cache-Control"] == "public, max-age=31536000, immutable"

            code, body, headers = request(opener, base, "/assets/index-EfGh5678.css")
            assert code == 200 and headers.get_content_type() == "text/css"
            assert headers["Cache-Control"].endswith("immutable")

            code, _, headers = request(opener, base, "/assets/brand.png")
            assert code == 200 and headers.get_content_type() == "image/png"
            assert headers["Cache-Control"] == "no-cache"

            code, body, _ = request(opener, base, "/assets/missing.js")
            assert code == 404 and b"RightThesis React" not in body
            code, body, _ = request(
                opener, base, "/assets/%2e%2e/%2e%2e/secret.txt",
            )
            assert code == 404 and b"must never be served" not in body
            code, body, _ = request(opener, base, "/assets/leak.txt")
            assert code == 404 and b"must never be served" not in body

            code, body, headers = request(opener, base, "/legacy")
            assert code == 200 and b'/legacy/app.js' in body
            assert headers.get_content_type() == "text/html"
            code, body, headers = request(opener, base, "/legacy/app.js")
            assert code == 200 and body
            assert headers.get_content_type() == "text/javascript"

            code, body, headers = request(opener, base, "/api/not-a-route")
            assert code == 404 and headers.get_content_type() == "application/json"
            assert b"RightThesis React" not in body
            code, body, headers = request(opener, base, "/api/config", method="HEAD")
            assert code == 405 and body == b""
            assert headers["Allow"] == "GET, POST"
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    run()
    print("✓ React 静态资源、SPA/HEAD、旧版入口与路径隔离全部正确")
