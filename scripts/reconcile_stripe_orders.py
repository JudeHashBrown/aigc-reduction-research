"""Reconcile live Stripe sessions/refunds and alert on unresolved disputes.

This job never creates charges or refunds. It verifies Stripe objects using the
server's restricted key, then applies the same idempotent credit ledger rules
as authenticated webhooks. A non-zero exit triggers the systemd mail alert.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from billing import BillingStore  # noqa: E402
from payments import StripePaymentProvider  # noqa: E402
from stripe_live_preflight import settings  # noqa: E402


def run(database: Path, *, skip_disputes: bool = False) -> int:
    config = settings()
    for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_LIVE_ENABLED", "PUBLIC_ORIGIN"):
        if name in config and name not in os.environ:
            os.environ[name] = config[name]
    store = BillingStore(database)
    provider = StripePaymentProvider(store)
    if not provider.configured or not provider.live:
        print("FAIL: Stripe 正式对账未配置")
        return 1
    checked = 0
    failed = 0
    disputes = 0
    for order in store.stripe_reconciliation_candidates():
        if not order["stripe_livemode"]:
            continue
        checked += 1
        try:
            provider.reconcile_order(order["account_id"], order["id"], audit_refunds=True)
            updated = store.stripe_order_for_reconciliation(order["account_id"], order["id"])
            if not skip_disputes and updated and updated["payment_intent_id"]:
                open_ids = provider.unresolved_disputes(updated["payment_intent_id"])
                if open_ids:
                    disputes += 1
                    print(f"ATTENTION: order {order['id']} has {len(open_ids)} unresolved Stripe dispute(s)")
        except Exception as exc:  # noqa: BLE001 - continue checking other orders
            failed += 1
            print(f"FAIL: order {order['id']} could not be reconciled ({type(exc).__name__})")
    if skip_disputes:
        print("WARNING: Stripe dispute monitoring disabled; restricted key lacks dispute-read permission")
    print(f"Stripe reconciliation: checked={checked} failed={failed} disputes={disputes}")
    return 1 if failed or disputes else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--skip-disputes", action="store_true",
                        help="Temporary: reconcile payments and refunds without dispute monitoring")
    args = parser.parse_args()
    return run(args.database, skip_disputes=args.skip_disputes)


if __name__ == "__main__":
    raise SystemExit(main())
