"""Aggregate first-party page views without retaining visitor identifiers."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo


TRACKED_ROUTES = frozenset({
    "/", "/pricing", "/auth", "/auth/verify", "/auth/forgot",
    "/legal/privacy", "/legal/terms", "/help",
    "/app", "/app/new", "/app/workbench", "/app/versions",
    "/app/billing", "/app/billing/usage", "/app/billing/orders",
    "/checkout/pro", "/app/settings/account", "/app/settings/service",
})
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class TrafficError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class TrafficStore:
    """Store only per-day, per-route page-view totals in the main backup database."""

    def __init__(self, path: Path | str, now: Callable[[], float] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or time.time
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS traffic_daily (
                day TEXT NOT NULL,
                path TEXT NOT NULL,
                views INTEGER NOT NULL CHECK(views >= 0),
                PRIMARY KEY(day, path)
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _today(self):
        return datetime.fromtimestamp(self._now(), _SHANGHAI).date()

    def record(self, path: str) -> None:
        """Count one rendered route. Reject URLs and arbitrary paths at the boundary."""
        if not isinstance(path, str) or path not in TRACKED_ROUTES:
            raise TrafficError("页面路径无效。")
        day = self._today().isoformat()
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO traffic_daily(day, path, views)
                    VALUES (?, ?, 1)
                    ON CONFLICT(day, path) DO UPDATE SET views=views+1""",
                    (day, path))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def overview(self, days: int = 7) -> dict:
        """Return a complete daily series and period totals for an admin view."""
        if type(days) is not int or days not in {7, 30, 90}:
            raise TrafficError("统计周期无效。")
        today = self._today()
        first_day = today - timedelta(days=days - 1)
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN")
                all_time = db.execute("""SELECT MIN(day) AS count_started_on,
                    COALESCE(SUM(views), 0) AS views FROM traffic_daily""").fetchone()
                daily_rows = db.execute("""SELECT day, SUM(views) AS views
                    FROM traffic_daily WHERE day BETWEEN ? AND ?
                    GROUP BY day ORDER BY day""",
                    (first_day.isoformat(), today.isoformat())).fetchall()
                top_rows = db.execute("""SELECT path, SUM(views) AS views
                    FROM traffic_daily WHERE day BETWEEN ? AND ?
                    GROUP BY path ORDER BY views DESC, path ASC LIMIT 10""",
                    (first_day.isoformat(), today.isoformat())).fetchall()
                db.commit()
            except Exception:
                db.rollback()
                raise
        by_day = {row["day"]: int(row["views"]) for row in daily_rows}
        daily = [
            {"date": (first_day + timedelta(days=offset)).isoformat(),
             "views": by_day.get((first_day + timedelta(days=offset)).isoformat(), 0)}
            for offset in range(days)
        ]
        return {
            "days": days,
            "from_date": first_day.isoformat(),
            "to_date": today.isoformat(),
            "today_views": daily[-1]["views"],
            "period_views": sum(item["views"] for item in daily),
            "all_time_views": int(all_time["views"]),
            "count_started_on": all_time["count_started_on"],
            "daily": daily,
            "top_pages": [{"path": row["path"], "views": int(row["views"])}
                          for row in top_rows],
        }
