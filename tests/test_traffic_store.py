"""Page-view totals are durable, bounded, and free of visitor identifiers."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
from traffic_store import TrafficError, TrafficStore  # noqa: E402


def run():
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "app.sqlite3"
        now = [datetime(2026, 10, 25, 15, 59, 59, tzinfo=timezone.utc).timestamp()]
        traffic = TrafficStore(database, now=lambda: now[0])
        traffic.record("/")
        traffic.record("/")
        now[0] += 1  # Midnight in Asia/Shanghai, still October 25 in UTC.
        traffic.record("/pricing")
        traffic.record("/checkout/pro")
        week = traffic.overview(7)
        assert week["days"] == 7
        assert week["from_date"] == "2026-10-20"
        assert week["to_date"] == "2026-10-26"
        assert week["count_started_on"] == "2026-10-25"
        assert week["today_views"] == 2
        assert week["period_views"] == week["all_time_views"] == 4
        assert len(week["daily"]) == 7
        assert week["daily"][-2:] == [
            {"date": "2026-10-25", "views": 2},
            {"date": "2026-10-26", "views": 2},
        ]
        assert week["top_pages"] == [
            {"path": "/", "views": 2},
            {"path": "/checkout/pro", "views": 1},
            {"path": "/pricing", "views": 1},
        ]
        assert TrafficStore(database, now=lambda: now[0]).overview(30)["all_time_views"] == 4

        for invalid in ("/admin", "/404", "/pricing?source=private",
                        "/app/documents/private-paper", "https://rightthesis.com/"):
            try:
                traffic.record(invalid)
            except TrafficError as exc:
                assert exc.status == 400
            else:
                raise AssertionError(f"unexpectedly accepted route {invalid}")
        for invalid in (0, 1, 8, 91, "7", True):
            try:
                traffic.overview(invalid)
            except TrafficError as exc:
                assert exc.status == 400
            else:
                raise AssertionError(f"unexpectedly accepted period {invalid}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(traffic.record, ["/app"] * 24))
        assert traffic.overview(7)["period_views"] == 28
        with sqlite3.connect(database) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(traffic_daily)")}
            assert columns == {"day", "path", "views"}
            assert db.execute("SELECT SUM(views) FROM traffic_daily").fetchone()[0] == 28

        now[0] += 8 * 86400
        later = traffic.overview(7)
        assert later["period_views"] == later["today_views"] == 0
        assert later["all_time_views"] == 28
        assert later["count_started_on"] == "2026-10-25"
        assert len(later["daily"]) == 7 and not later["top_pages"]


if __name__ == "__main__":
    run()
    print("✓ 访问量按上海日期汇总且不保存访客标识")
