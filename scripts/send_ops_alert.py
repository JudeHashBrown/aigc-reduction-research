"""Send a minimal backup failure notice using the existing SMTP credentials."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from auth import EmailDelivery  # noqa: E402

ALLOWED = {"AUTH_EMAIL_DELIVERY", "AUTH_EMAIL_FROM", "AUTH_SMTP_HOST",
           "AUTH_SMTP_PORT", "AUTH_SMTP_USERNAME", "AUTH_SMTP_PASSWORD",
           "AUTH_SMTP_SSL", "AUTH_SMTP_STARTTLS", "AUTH_SMTP_PROXY_URL",
           "ADMIN_EMAILS"}


def read_env(path: Path) -> dict:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name not in ALLOWED:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--test", action="store_true", help="send a clearly labelled test notice")
    args = parser.parse_args()
    if not args.unit.startswith("rightthesis-") or not args.unit.endswith(".service"):
        parser.error("unexpected unit name")
    os.environ.update(read_env(args.env_file))
    recipients = [value.strip() for value in os.environ.get("ADMIN_EMAILS", "").split(",") if value.strip()]
    if not recipients:
        raise RuntimeError("ADMIN_EMAILS has no alert recipient")
    sender = EmailDelivery.from_env()
    label = "备份告警测试" if args.test else "备份告警"
    message = (
        f"这是一封测试邮件：{args.unit} 的故障告警通道可用；没有发生备份故障。\n"
        if args.test else
        f"{args.unit} 执行失败。请登录香港服务器查看 systemctl status 与 journalctl 日志。\n"
    )
    for recipient in recipients:
        sender.send_operational_alert(
            recipient, f"RightThesis {label}：{args.unit}",
            message + "不要通过邮件发送备份密钥或论文内容。\n",
        )
    print(f"backup {'test ' if args.test else ''}alert sent to {len(recipients)} operator(s)")


if __name__ == "__main__":
    main()
