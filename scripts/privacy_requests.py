"""Review and fulfill authenticated account-deletion requests safely.

Fulfillment removes account identity and manuscript content, while preserving
pseudonymous order and usage records for financial reconciliation. It refuses
accounts with running jobs, pending payments or unused paid credits.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from backup_database import verify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
from privacy_store import PrivacyStore  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    fulfill = commands.add_parser("fulfill")
    fulfill.add_argument("--request-id", required=True)
    fulfill.add_argument("--verified-backup", type=Path, required=True)
    fulfill.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    store = PrivacyStore(args.database)
    if args.action == "list":
        print(json.dumps(store.pending_requests(), ensure_ascii=False, indent=2))
        return
    archive = args.verified_backup
    if not archive.is_file() or time.time() - archive.stat().st_mtime > 24 * 3600:
        raise SystemExit("refusing deletion without a backup created in the past 24 hours")
    verify(archive, args.key_file)
    result = store.complete_deletion(args.request_id)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
