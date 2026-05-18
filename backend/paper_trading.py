"""
paper_trading.py — Persistent paper trading engine.

Replaces the fake "ORD<timestamp>" order IDs in /confirm-trade with real,
SQLite-backed trade records. Implements FIFO lot matching so SELL trades
realize P&L against the oldest open BUYs for the same symbol.

This module is what makes the "real trades" story credible in code review:
every trade the user places is persisted, has a unique sequential order ID,
and survives server restart. Prompt C (next) feeds these session trades into
the Gemma behavioral analysis instead of seeded demo-only examples in
broker_client.get_trading_context().

Design notes:
- Single table `paper_trades`. Each trade row tracks `quantity_remaining` so
  partial closes don't require splitting rows.
- Realized P&L is recorded on the *closing* leg (the SELL in a long round-trip).
  Summing realized_pnl across all rows therefore avoids double-counting.
- Trade matching is FIFO: oldest open BUYs close first when a SELL arrives.
- If a SELL has unmatched quantity left after walking all open BUYs, the
  remainder is recorded as a new open SHORT position. The reverse holds for
  BUYs that would close open SHORTs — this engine handles both directions.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from models import Trade, MarginData

# Two SQLite databases, one per non-Kite mode. Demo is auto-seeded with the
# canonical high-risk session; Paper starts empty and the user builds it up.
# Live Kite mode bypasses both — see kite_client.py.
DB_DIR = Path("data")
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATHS = {
    "demo":  DB_DIR / "paper_trading_demo.db",
    "paper": DB_DIR / "paper_trading_user.db",
}

# Backward-compat alias (some callers still import DB_PATH directly).
DB_PATH = DB_PATHS["demo"]


def _db_path(mode: str = "demo") -> Path:
    """Resolve the SQLite path for a given mode. Falls back to demo for safety."""
    return DB_PATHS.get(mode, DB_PATHS["demo"])


# SQLite is thread-safe per-connection but we serialize writes from FastAPI
# worker threads via this lock to keep the matching logic atomic without
# bumping isolation level or worrying about retries.
_write_lock = threading.Lock()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db(mode: str = "demo") -> None:
    with sqlite3.connect(_db_path(mode)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id            TEXT UNIQUE NOT NULL,
                symbol              TEXT NOT NULL,
                action              TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
                quantity            INTEGER NOT NULL,
                price               REAL NOT NULL,
                timestamp           TEXT NOT NULL,
                quantity_remaining  INTEGER NOT NULL,
                realized_pnl        REAL,
                is_loss             INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol_open
            ON paper_trades(symbol, action, quantity_remaining)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_trades_ts
            ON paper_trades(timestamp DESC)
        """)


# ── Order ID generator ────────────────────────────────────────────────────────

def _next_order_id(conn: sqlite3.Connection) -> str:
    """Format: ORD<UTC date>-<6-digit sequence>. Stable, sortable, human-readable."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE order_id LIKE ?",
        (f"ORD{today}-%",),
    ).fetchone()[0]
    return f"ORD{today}-{seq + 1:06d}"


# ── Trade insertion + FIFO matching ───────────────────────────────────────────

def record_trade(
    symbol: str,
    action: str,
    quantity: int,
    price: float,
    mode: str = "demo",
) -> dict[str, Any]:
    """
    Persist a paper trade. If it closes any opposite open positions on the
    same symbol, those are matched FIFO and realized P&L is computed.

    Returns: {
      order_id, status ('open'|'closed'|'partial'),
      realized_pnl, matched_count, quantity_remaining
    }
    """
    if action not in ("BUY", "SELL"):
        raise ValueError(f"action must be BUY or SELL, got {action!r}")
    if quantity <= 0 or price <= 0:
        raise ValueError(f"quantity and price must be positive (got {quantity}, {price})")

    init_db(mode)
    now_iso = datetime.now(timezone.utc).isoformat()
    opposite = "SELL" if action == "BUY" else "BUY"

    with _write_lock, sqlite3.connect(_db_path(mode)) as conn:
        conn.row_factory = sqlite3.Row
        order_id = _next_order_id(conn)

        # Find open opposite-side legs on this symbol, oldest first.
        opens = conn.execute(
            """
            SELECT id, quantity_remaining, price
              FROM paper_trades
             WHERE symbol = ? AND action = ? AND quantity_remaining > 0
             ORDER BY timestamp ASC
            """,
            (symbol, opposite),
        ).fetchall()

        remaining = quantity
        realized_pnl = 0.0
        matched_count = 0

        for row in opens:
            if remaining <= 0:
                break
            take = min(remaining, row["quantity_remaining"])

            # Per-share P&L direction: long round-trip → (sell - buy)
            #                          short round-trip → (sell - buy) too
            # The closing leg's price minus the opening leg's price, times qty.
            if action == "SELL":   # closing a long BUY
                lot_pnl = (price - row["price"]) * take
            else:                  # action == "BUY", closing a short SELL
                lot_pnl = (row["price"] - price) * take

            realized_pnl += lot_pnl
            matched_count += 1
            remaining -= take

            new_remaining = row["quantity_remaining"] - take
            conn.execute(
                "UPDATE paper_trades SET quantity_remaining = ? WHERE id = ?",
                (new_remaining, row["id"]),
            )

        # Determine the new trade's status.
        if matched_count == 0:
            status = "open"          # nothing on the other side — pure new position
        elif remaining == 0:
            status = "closed"        # this trade fully matched against the book
        else:
            status = "partial"       # matched some, opened the rest as a new position

        conn.execute(
            """
            INSERT INTO paper_trades
                (order_id, symbol, action, quantity, price, timestamp,
                 quantity_remaining, realized_pnl, is_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id, symbol, action, quantity, price, now_iso,
                remaining,                          # carries forward as new open lot
                realized_pnl if matched_count else None,
                1 if (matched_count and realized_pnl < 0) else (0 if matched_count else None),
            ),
        )

        return {
            "order_id": order_id,
            "status": status,
            "realized_pnl": round(realized_pnl, 2) if matched_count else None,
            "matched_count": matched_count,
            "quantity_remaining": remaining,
        }


# ── Read APIs ─────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "order_id": row["order_id"],
        "symbol": row["symbol"],
        "action": row["action"],
        "quantity": row["quantity"],
        "price": row["price"],
        "timestamp": row["timestamp"],
        "quantity_remaining": row["quantity_remaining"],
        "realized_pnl": row["realized_pnl"],
        "is_loss": bool(row["is_loss"]) if row["is_loss"] is not None else None,
    }


def get_recent_trades(limit: int = 20, mode: str = "demo") -> list[dict[str, Any]]:
    """Most-recent-first list for the 'Today's Trades' panel."""
    init_db(mode)
    with sqlite3.connect(_db_path(mode)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM paper_trades ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_open_positions(mode: str = "demo") -> list[dict[str, Any]]:
    """Aggregated open quantity per symbol, weighted-average entry price."""
    init_db(mode)
    with sqlite3.connect(_db_path(mode)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT symbol, action,
                   SUM(quantity_remaining)            AS qty_open,
                   SUM(quantity_remaining * price) /
                       NULLIF(SUM(quantity_remaining), 0) AS avg_price
              FROM paper_trades
             WHERE quantity_remaining > 0
             GROUP BY symbol, action
            """
        ).fetchall()
    return [
        {
            "symbol": r["symbol"],
            "side":   r["action"],          # BUY = long, SELL = short
            "quantity": r["qty_open"],
            "avg_price": round(r["avg_price"], 2) if r["avg_price"] else 0.0,
        }
        for r in rows
    ]


def get_session_pnl(since: datetime | None = None, mode: str = "demo") -> dict[str, Any]:
    """Realized P&L since `since` (default: start of UTC today)."""
    init_db(mode)
    if since is None:
        now = datetime.now(timezone.utc)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    with sqlite3.connect(_db_path(mode)) as conn:
        conn.row_factory = sqlite3.Row
        agg = conn.execute(
            """
            SELECT
                COUNT(*)                                    AS total_trades,
                SUM(CASE WHEN realized_pnl IS NOT NULL THEN 1 ELSE 0 END)
                                                             AS closed_trades,
                COALESCE(SUM(realized_pnl), 0)              AS realized_pnl,
                SUM(CASE WHEN is_loss = 1 THEN 1 ELSE 0 END) AS loss_count
              FROM paper_trades
             WHERE timestamp >= ?
            """,
            (since.isoformat(),),
        ).fetchone()

    return {
        "since": since.isoformat(),
        "total_trades":   agg["total_trades"],
        "closed_trades":  agg["closed_trades"],
        "realized_pnl":   round(agg["realized_pnl"], 2),
        "loss_count":     agg["loss_count"],
    }


def get_session_trades_for_ai(since_minutes: int = 240, mode: str = "demo") -> list[Trade]:
    """
    Recent session legs shaped as pydantic Trade for the Gemma prompt.

    Closed legs represent completed round-trips with realized P&L. Open legs
    are also included with pnl=None so Gemma can see that the user has placed
    trades even before those positions are closed. Fully matched entry legs
    are omitted to avoid double-counting a completed round-trip.

    Ordering: oldest first (matches how broker_client builds context).
    """
    init_db(mode)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    with sqlite3.connect(_db_path(mode)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM paper_trades
             WHERE (
                    realized_pnl IS NOT NULL
                    AND timestamp >= ?
               )
                OR quantity_remaining > 0
             ORDER BY timestamp ASC
            """,
            (cutoff.isoformat(),),
        ).fetchall()

    out: list[Trade] = []
    for r in rows:
        is_open = r["realized_pnl"] is None
        out.append(
            Trade(
                trade_id=r["order_id"],
                symbol=r["symbol"],
                action=r["action"],
                quantity=r["quantity_remaining"] if is_open else r["quantity"],
                price=r["price"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                pnl=None if is_open else r["realized_pnl"],
                is_loss=False if is_open else (
                    bool(r["is_loss"]) if r["is_loss"] is not None else False
                ),
            )
        )
    return out


# ── Margin derivation from open positions ─────────────────────────────────────

def compute_margin(total: float = 100_000.0, mode: str = "demo") -> MarginData:
    """
    Derive a MarginData snapshot from the current open paper positions.

    Long exposure (open BUYs) consumes margin. Short exposure (open SELLs)
    is treated symmetrically — both lock up capital in a paper account.
    `total` is the user's notional capital ceiling (₹100K default).
    """
    init_db(mode)
    with sqlite3.connect(_db_path(mode)) as conn:
        used = conn.execute(
            """
            SELECT COALESCE(SUM(quantity_remaining * price), 0)
              FROM paper_trades
             WHERE quantity_remaining > 0
            """
        ).fetchone()[0]

    used = float(used)
    used_clamped = min(used, total)            # paper account can't exceed notional
    available    = max(0.0, total - used_clamped)

    return MarginData(
        available=round(available, 2),
        used=round(used_clamped, 2),
        total=round(total, 2),
    )


# ── Demo session seeding ──────────────────────────────────────────────────────

def reset_db(mode: str = "paper") -> dict[str, Any]:
    """
    Wipe ALL trades from the given mode's database. Used by /paper/reset.
    Default mode is "paper" because we don't want accidental demo wipes.
    """
    path = _db_path(mode)
    with _write_lock:
        if path.exists():
            path.unlink()
        init_db(mode)
    return {"reset": True, "mode": mode, "path": str(path)}


def has_session_trades(within_minutes: int = 1440, mode: str = "demo") -> bool:
    """True if any paper_trades row falls inside the lookback window."""
    init_db(mode)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    with sqlite3.connect(_db_path(mode)) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE timestamp >= ?",
            (cutoff.isoformat(),),
        ).fetchone()[0]
    return n > 0


# A realistic high-risk session: 4 losing round-trips + 1 winning round-trip
# + 2 still-open BUYs that drive margin usage above 70%. Times are minutes
# before "now" so the session feels like the last 45 minutes of trading.
#
# Each tuple: (symbol, side, qty, entry_price, exit_price_or_none, minutes_ago)
#  - exit_price=None → leg stays open (drives margin)
_DEMO_SESSION: list[tuple[str, str, int, float, float | None, int]] = [
    # 4 losing round-trips (BUY → SELL at lower price)
    ("NIFTY24DEC23000CE",     "BUY",  75, 245.00, 202.33, 38),  # -3200
    ("RELIANCE",              "BUY",  10, 1330.00, 1185.00, 30),  # -1450
    ("BANKNIFTY24DEC49000PE", "BUY",  25, 180.00, 16.00,  20),  # -4100
    ("INFY",                  "BUY",  15, 1540.00, 1480.67, 12),  # -890
    # 1 winning round-trip
    ("TATAMOTORS",            "BUY",  20, 920.00,  980.00,   5),  # +1200
    # 2 still-open BUYs that consume margin (~₹85K)
    ("NIFTY24DEC23000CE",     "BUY", 300, 220.00,  None,     3),  # ₹66,000 open
    ("HDFCBANK",              "BUY",  10, 1900.00, None,     1),  # ₹19,000 open
]


def seed_demo_trades(mode: str = "demo") -> dict[str, int]:
    """
    Populate paper_trades with a realistic high-risk demo session if no
    trades exist in the last 24 hours. Idempotent — safe to call repeatedly.

    Returns a summary of what was inserted (or skipped).
    """
    if has_session_trades(mode=mode):
        return {"inserted": 0, "skipped": True}

    init_db(mode)
    now = datetime.now(timezone.utc)
    inserted = 0

    with _write_lock, sqlite3.connect(_db_path(mode)) as conn:
        for symbol, side, qty, entry_price, exit_price, mins_ago in _DEMO_SESSION:
            entry_ts = (now - timedelta(minutes=mins_ago)).isoformat()
            entry_id = _next_order_id(conn)
            conn.execute(
                """
                INSERT INTO paper_trades
                    (order_id, symbol, action, quantity, price, timestamp,
                     quantity_remaining, realized_pnl, is_loss)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (entry_id, symbol, side, qty, entry_price, entry_ts, qty),
            )
            inserted += 1

            if exit_price is None:
                continue   # leg stays open

            # Close the entry with an exit leg ~45-90 seconds later.
            opp = "SELL" if side == "BUY" else "BUY"
            exit_ts = (now - timedelta(minutes=mins_ago) + timedelta(seconds=75)).isoformat()
            pnl = (exit_price - entry_price) * qty if side == "BUY" else (entry_price - exit_price) * qty
            exit_id = _next_order_id(conn)

            # Close the entry leg
            conn.execute(
                "UPDATE paper_trades SET quantity_remaining = 0 WHERE order_id = ?",
                (entry_id,),
            )
            # Insert the closing leg with realized P&L
            conn.execute(
                """
                INSERT INTO paper_trades
                    (order_id, symbol, action, quantity, price, timestamp,
                     quantity_remaining, realized_pnl, is_loss)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (exit_id, symbol, opp, qty, exit_price, exit_ts,
                 round(pnl, 2), 1 if pnl < 0 else 0),
            )
            inserted += 1

    return {"inserted": inserted, "skipped": False}


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    init_db()

    print("BUY  10 RELIANCE @ 1300:", record_trade("RELIANCE", "BUY",  10, 1300.0))
    print("BUY  10 RELIANCE @ 1310:", record_trade("RELIANCE", "BUY",  10, 1310.0))
    print("SELL 15 RELIANCE @ 1280:", record_trade("RELIANCE", "SELL", 15, 1280.0))

    print("\nOpen positions:")
    print(json.dumps(get_open_positions(), indent=2))
    print("\nSession P&L:")
    print(json.dumps(get_session_pnl(), indent=2))
    print("\nRecent trades:")
    print(json.dumps(get_recent_trades(), indent=2))
