"""Shared helpers for stdlib HTTP integration tests."""
from __future__ import annotations

import http.cookiejar
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def opener_with_cookies():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar),
    ), jar


def request(opener, base, path, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = dict(headers or {})
    if payload is not None:
        merged.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(base + path, data=body, headers=merged)
    try:
        with opener.open(req, timeout=12) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"_raw": raw.decode("utf-8", "replace")}
        return exc.code, parsed, exc.headers


def wait_until_ready(opener, base, proc):
    deadline = time.time() + 12
    while time.time() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"trial server exited early: {output}")
        try:
            code, _, _ = request(opener, base, "/health")
            if code == 200:
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("trial server did not become ready")


def stop_server(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    output = proc.stdout.read() if proc.stdout else ""
    if "[request handler failed]" in output.lower():
        raise AssertionError(output[-1200:])
