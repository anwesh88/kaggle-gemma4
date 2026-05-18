"""
kite_client.py - Live Kite Connect adapter for Finsight OS.

Wraps the official `kiteconnect` SDK so the FastAPI layer can:
  - Generate the Zerodha login URL
  - Handle the backend OAuth callback after login
  - Persist the resulting access token both in memory and encrypted on disk
  - Auto-restore the last valid session on backend startup
  - Read holdings, positions, trades, quotes, profile, and margins
  - Place real orders after the Mindful Speed Bump flow succeeds
  - Normalize Kite payloads into the app's internal shapes
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

try:
    from kiteconnect import KiteConnect  # type: ignore
    from kiteconnect.exceptions import (  # type: ignore
        GeneralException,
        NetworkException,
        TokenException,
    )
    KITECONNECT_AVAILABLE = True
except ImportError:
    KITECONNECT_AVAILABLE = False
    KiteConnect = None  # type: ignore
    TokenException = NetworkException = GeneralException = Exception  # type: ignore

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    InvalidToken = Exception  # type: ignore

logger = logging.getLogger(__name__)

KITE_API_KEY = os.getenv("KITE_API_KEY", "").strip()
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000").strip()
KITE_REDIRECT_URL = os.getenv(
    "KITE_REDIRECT_URL",
    f"http://localhost:{BACKEND_PORT}/kite/callback",
).strip()
PAPER_CAPITAL = float(os.getenv("PAPER_CAPITAL", "100000"))

KITE_CONFIGURED = bool(KITE_API_KEY and KITE_API_SECRET and KITECONNECT_AVAILABLE)

DEFAULT_WATCHLIST = [
    "NSE:RELIANCE",
    "NSE:INFY",
    "NSE:TCS",
    "NSE:HDFCBANK",
    "NSE:NIFTY 50",
]


def extract_request_token(s: str) -> str | None:
    """
    Accept either a bare request_token or the full broken-redirect URL the
    user copied out of their browser bar and return the bare token string.
    """
    if not s:
        return None
    s = s.strip()
    if s.startswith(("http://", "https://")) or "?" in s or "request_token=" in s:
        from urllib.parse import parse_qs

        try:
            parsed = urlparse(s if "://" in s else f"http://x/?{s}")
            qs = parse_qs(parsed.query)
            tok = qs.get("request_token", [""])[0].strip()
            if tok:
                return tok
        except Exception:
            pass
    if s.isalnum() and 16 <= len(s) <= 64:
        return s
    return None


_KITE_DATA_DIR = Path("data")
_KITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
_KITE_KEY_PATH = _KITE_DATA_DIR / "kite_secret.key"
_KITE_TOKEN_PATH = _KITE_DATA_DIR / "kite_access_token.encrypted"


@dataclass
class KiteSession:
    access_token: str
    user_id: str
    user_name: str
    email: str | None = None
    issued_at: float = field(default_factory=time.time)
    public_token: str | None = None
    source: str = "cookie"


class SecureTokenStorage:
    """Fernet-encrypted on-disk persistence for the Kite access token."""

    def __init__(self, key_file: Path = _KITE_KEY_PATH, token_file: Path = _KITE_TOKEN_PATH):
        self.key_file = Path(key_file)
        self.token_file = Path(token_file)

    def _ensure_key_exists(self) -> None:
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography package not installed - pip install cryptography")
        if not self.key_file.exists():
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            self.key_file.write_bytes(Fernet.generate_key())
            logger.info(f"[kite] Created new Fernet key at {self.key_file}")

    def _cipher(self) -> "Fernet":
        return Fernet(self.key_file.read_bytes())

    def save_token(self, token: str, profile: dict[str, Any] | None = None) -> bool:
        try:
            self._ensure_key_exists()
            self.token_file.write_bytes(self._cipher().encrypt(token.encode()))
            if profile:
                import json

                self.token_file.with_suffix(".profile.json").write_text(
                    json.dumps(profile, ensure_ascii=False),
                    encoding="utf-8",
                )
            logger.info("[kite] Access token encrypted and saved")
            return True
        except Exception as exc:
            logger.error(f"[kite] Failed to save token: {exc}")
            return False

    def load_token(self) -> str | None:
        if not self.token_file.exists() or not self.key_file.exists():
            return None
        try:
            return self._cipher().decrypt(self.token_file.read_bytes()).decode()
        except (InvalidToken, Exception) as exc:
            logger.warning(f"[kite] Could not decrypt saved token: {exc}")
            return None

    def load_profile(self) -> dict[str, Any] | None:
        path = self.token_file.with_suffix(".profile.json")
        if not path.exists():
            return None
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def clear(self) -> None:
        for path in (self.token_file, self.token_file.with_suffix(".profile.json")):
            try:
                if path.exists():
                    path.unlink()
            except Exception as exc:
                logger.warning(f"[kite] Failed to remove {path}: {exc}")


_storage = SecureTokenStorage()
_sessions: dict[str, KiteSession] = {}
PERSISTED_SESSION_ID = "persisted-disk-session"

_RATE_SEM = asyncio.Semaphore(3)
_RATE_DELAY = 0.34


def _ensure_lib() -> None:
    if not KITECONNECT_AVAILABLE:
        raise RuntimeError(
            "kiteconnect package not installed. "
            "Run `pip install kiteconnect` in the backend venv to enable Live Kite mode."
        )


def expected_redirect_url() -> str:
    return KITE_REDIRECT_URL or f"http://localhost:{BACKEND_PORT}/kite/callback"


def redirect_diagnostics(request_base_url: str | None = None) -> dict[str, Any]:
    expected = expected_redirect_url()
    warning_parts: list[str] = []

    expected_host = urlparse(expected).hostname or ""
    frontend_host = urlparse(FRONTEND_URL).hostname or ""
    request_host = (urlparse(request_base_url).hostname or "") if request_base_url else ""

    if {expected_host, frontend_host} != {"localhost"}:
        warning_parts.append(
            "Use localhost consistently for local Kite OAuth. "
            f"Frontend should be {FRONTEND_URL} and the registered redirect should be {expected}."
        )

    if request_host and request_host != "localhost":
        warning_parts.append(
            f"You opened the backend on {request_host}. "
            f"For browser login, open the app on {FRONTEND_URL} and register {expected} in Kite."
        )

    if "127.0.0.1" in {expected_host, frontend_host, request_host}:
        warning_parts.append(
            f"Redirects to 127.0.0.1 often look like login failures in the browser. "
            f"Register the Kite redirect URL exactly as {expected}."
        )

    return {
        "expected_redirect_url": expected,
        "frontend_url": FRONTEND_URL,
        "warning": " ".join(dict.fromkeys(warning_parts)) or None,
    }


def is_configured() -> bool:
    return KITE_CONFIGURED


def is_authenticated(session_id: str | None) -> bool:
    return session_id is not None and session_id in _sessions


def status_dict(
    session_id: str | None,
    *,
    cookie_present: bool = False,
    request_base_url: str | None = None,
) -> dict[str, Any]:
    diag = redirect_diagnostics(request_base_url=request_base_url)

    if not is_configured():
        return {
            "configured": False,
            "authenticated": False,
            "error": "KITE_API_KEY and KITE_API_SECRET must be set in backend/.env",
            "session_source": None,
            **diag,
        }

    sess = _sessions.get(session_id) if session_id else None
    if sess is None:
        return {
            "configured": True,
            "authenticated": False,
            "session_source": None,
            **diag,
        }

    if cookie_present:
        session_source = "cookie"
    elif sess.source == "restored_disk":
        session_source = "restored_disk"
    else:
        session_source = sess.source or "cookie"

    return {
        "configured": True,
        "authenticated": True,
        "user_id": sess.user_id,
        "user_name": sess.user_name,
        "session_source": session_source,
        **diag,
    }


def login_url() -> str:
    _ensure_lib()
    kite = KiteConnect(api_key=KITE_API_KEY)  # type: ignore[call-arg]
    return kite.login_url()


def handle_callback(request_token: str, source: str = "cookie") -> tuple[str, KiteSession]:
    """
    Exchange the single-use request_token for a long-lived access_token and
    persist the resulting session for browser and restart recovery.
    """
    _ensure_lib()
    kite = KiteConnect(api_key=KITE_API_KEY)  # type: ignore[call-arg]
    try:
        data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    except TokenException as exc:
        raise PermissionError(f"Kite rejected the request_token: {exc}")

    sess = KiteSession(
        access_token=data["access_token"],
        user_id=data.get("user_id", ""),
        user_name=data.get("user_name", ""),
        email=data.get("email"),
        public_token=data.get("public_token"),
        source=source,
    )
    sid = PERSISTED_SESSION_ID
    _sessions[sid] = sess

    _storage.save_token(
        sess.access_token,
        profile={
            "user_id":   sess.user_id,
            "user_name": sess.user_name,
            "email":     sess.email,
            "issued_at": sess.issued_at,  # used by daily IST re-auth gate
        },
    )
    return sid, sess


def logout(session_id: str | None) -> None:
    if session_id:
        _sessions.pop(session_id, None)
    _sessions.pop(PERSISTED_SESSION_ID, None)
    _storage.clear()


def restore_session_from_disk() -> KiteSession | None:
    if not is_configured():
        return None
    token = _storage.load_token()
    if not token:
        return None

    _ensure_lib()
    try:
        kite = KiteConnect(api_key=KITE_API_KEY)  # type: ignore[call-arg]
        kite.set_access_token(token)
        profile = kite.profile()
    except TokenException:
        logger.info("[kite] Saved token expired (daily 6 AM IST) - clearing")
        _storage.clear()
        return None
    except Exception as exc:
        logger.warning(f"[kite] Saved-token validation failed: {exc}")
        return None

    saved_profile = _storage.load_profile() or {}
    saved_issued_at = float(saved_profile.get("issued_at", 0) or 0)

    # Enforce daily IST re-auth: if the persisted issued_at falls on a
    # previous IST calendar day, refuse to restore even if Kite still accepts
    # the token. The user is forced through the login flow once per trading day.
    if saved_issued_at:
        issued_ist_date = datetime.fromtimestamp(saved_issued_at, tz=IST).date().isoformat()
        if issued_ist_date != _ist_today_iso():
            logger.info(
                f"[kite] Saved session from {issued_ist_date} is older than today's IST date — "
                "wiping and forcing fresh login (daily re-auth policy)."
            )
            _storage.clear()
            return None

    sess = KiteSession(
        access_token=token,
        user_id=profile.get("user_id", saved_profile.get("user_id", "")),
        user_name=profile.get("user_name", saved_profile.get("user_name", "")),
        email=profile.get("email", saved_profile.get("email")),
        issued_at=saved_issued_at or time.time(),
        source="restored_disk",
    )
    _sessions[PERSISTED_SESSION_ID] = sess
    logger.info(f"[kite] Restored session from disk for user: {sess.user_name}")
    return sess


def validate_session(session_id: str | None) -> bool:
    if not session_id or session_id not in _sessions:
        return False
    sess = _sessions[session_id]
    # Daily IST gate — sessions older than today's IST date are rejected even
    # if Kite would still accept the token. Forces a fresh login per day.
    if not session_is_today(sess):
        logger.info(f"[kite] Session {session_id[:8]}... is from a previous IST day — invalidating.")
        logout(session_id)
        return False
    _ensure_lib()
    try:
        kite = KiteConnect(api_key=KITE_API_KEY)  # type: ignore[call-arg]
        kite.set_access_token(sess.access_token)
        kite.profile()
        return True
    except TokenException:
        logger.info(f"[kite] Session {session_id[:8]}... expired during validate")
        logout(session_id)
        return False
    except Exception:
        return False


def _get_kite(session_id: str) -> KiteConnect:  # type: ignore[valid-type]
    _ensure_lib()
    sess = _sessions.get(session_id)
    if sess is None:
        raise PermissionError("Kite session not found - re-login required.")
    kite = KiteConnect(api_key=KITE_API_KEY)  # type: ignore[call-arg]
    kite.set_access_token(sess.access_token)
    return kite


async def _call(session_id: str, fn_name: str, *args, **kwargs) -> Any:
    async with _RATE_SEM:
        loop = asyncio.get_event_loop()
        try:
            kite = _get_kite(session_id)
            method = getattr(kite, fn_name)
            result = await loop.run_in_executor(None, lambda: method(*args, **kwargs))
        except TokenException:
            logout(session_id)
            raise PermissionError("Kite access_token expired - please log in again.")
        finally:
            await asyncio.sleep(_RATE_DELAY)
        return result


async def get_profile(session_id: str) -> dict[str, Any]:
    return await _call(session_id, "profile")


async def get_margins(session_id: str) -> dict[str, Any]:
    return await _call(session_id, "margins")


async def get_holdings(session_id: str) -> list[dict[str, Any]]:
    return await _call(session_id, "holdings")


async def get_positions(session_id: str) -> dict[str, Any]:
    return await _call(session_id, "positions")


async def get_orders(session_id: str) -> list[dict[str, Any]]:
    return await _call(session_id, "orders")


async def get_trades(session_id: str) -> list[dict[str, Any]]:
    return await _call(session_id, "trades")


async def get_quote(session_id: str, instruments: list[str]) -> dict[str, Any]:
    return await _call(session_id, "quote", instruments)


async def place_order(
    session_id: str,
    symbol: str,
    quantity: int,
    price: float,
    transaction_type: str,
    exchange: str = "NSE",
    product: str = "MIS",
    order_type: str = "LIMIT",
    variety: str = "regular",
) -> dict[str, Any]:
    return await _call(
        session_id,
        "place_order",
        variety=variety,
        exchange=exchange,
        tradingsymbol=symbol,
        transaction_type=transaction_type,
        quantity=int(quantity),
        product=product,
        order_type=order_type,
        price=float(price) if order_type != "MARKET" else None,
        market_protection=-1,
    )


async def cancel_order(session_id: str, order_id: str, variety: str = "regular") -> dict[str, Any]:
    return await _call(session_id, "cancel_order", variety=variety, order_id=order_id)


# ── Instruments cache (for stock search) ─────────────────────────────────────
# Kite ships a daily ~3MB CSV of every tradable instrument. We pull it once a
# day, cache it on disk, and serve fuzzy in-memory searches against it. The
# refresh is gated on the file's mtime so a fresh login auto-rotates the cache.

_INSTRUMENTS_PATH = _KITE_DATA_DIR / "instruments_nse.json"
_INSTRUMENTS_CACHE: list[dict[str, Any]] = []
_INSTRUMENTS_LOADED_AT: float = 0.0


async def _refresh_instruments(session_id: str) -> list[dict[str, Any]]:
    """Pull NSE instruments via kite.instruments('NSE') and persist."""
    import json
    raw = await _call(session_id, "instruments", "NSE")
    # We only need a handful of fields per row; keep the JSON tiny.
    slim = [
        {
            "instrument_token": r.get("instrument_token"),
            "tradingsymbol":    r.get("tradingsymbol"),
            "name":             r.get("name") or "",
            "segment":          r.get("segment"),
            "exchange":         r.get("exchange"),
            "instrument_type":  r.get("instrument_type"),
            "lot_size":         r.get("lot_size", 1),
        }
        for r in raw or []
        if r.get("instrument_type") in {"EQ", "FUT", "CE", "PE"}
    ]
    try:
        _INSTRUMENTS_PATH.write_text(json.dumps(slim), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[kite] Could not persist instruments cache: {e}")
    return slim


async def get_instruments(session_id: str, max_age_hours: float = 12) -> list[dict[str, Any]]:
    """Return cached NSE instruments, refreshing once a day."""
    global _INSTRUMENTS_CACHE, _INSTRUMENTS_LOADED_AT
    now = time.time()

    if _INSTRUMENTS_CACHE and (now - _INSTRUMENTS_LOADED_AT) < max_age_hours * 3600:
        return _INSTRUMENTS_CACHE

    # Try the on-disk cache first
    if _INSTRUMENTS_PATH.exists():
        try:
            mtime = _INSTRUMENTS_PATH.stat().st_mtime
            if (now - mtime) < max_age_hours * 3600:
                import json
                _INSTRUMENTS_CACHE = json.loads(_INSTRUMENTS_PATH.read_text(encoding="utf-8"))
                _INSTRUMENTS_LOADED_AT = now
                return _INSTRUMENTS_CACHE
        except Exception as e:
            logger.warning(f"[kite] Instruments cache unreadable: {e}")

    # Refresh from Kite
    _INSTRUMENTS_CACHE = await _refresh_instruments(session_id)
    _INSTRUMENTS_LOADED_AT = now
    return _INSTRUMENTS_CACHE


async def search_instruments(session_id: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Fuzzy stock search over the cached instruments. Matches on tradingsymbol
    (prefix-priority) and company name (substring). Equity rows ranked first.
    """
    q = (query or "").strip().upper()
    if not q:
        return []
    rows = await get_instruments(session_id)

    def score(row: dict[str, Any]) -> int:
        sym  = (row.get("tradingsymbol") or "").upper()
        name = (row.get("name") or "").upper()
        itype = (row.get("instrument_type") or "")
        # Tighter matches first
        s = 0
        if sym == q:                          s += 200
        elif sym.startswith(q):               s += 120
        elif q in sym:                        s +=  60
        if name.startswith(q):                s +=  40
        elif q in name:                       s +=  20
        if itype == "EQ":                     s +=  15   # equity over derivatives by default
        return s

    matches = [(score(r), r) for r in rows if q in (r.get("tradingsymbol") or "").upper()
                                              or q in (r.get("name") or "").upper()]
    matches.sort(key=lambda x: -x[0])
    return [r for _, r in matches[:limit]]


# ── Daily re-auth gate ────────────────────────────────────────────────────────
# Kite tokens expire at ~6 AM IST. We additionally enforce that the saved
# session is from *today's* IST calendar date — anything older is dropped
# the moment the user opens the app, forcing a fresh login.

from datetime import timedelta as _td

IST = timezone(_td(hours=5, minutes=30))


def _ist_today_iso() -> str:
    return datetime.now(IST).date().isoformat()


def session_is_today(sess: KiteSession | None) -> bool:
    """True iff sess was issued during the current IST trading day."""
    if not sess or not getattr(sess, "issued_at", None):
        return False
    issued_ist_date = datetime.fromtimestamp(sess.issued_at, tz=IST).date().isoformat()
    return issued_ist_date == _ist_today_iso()


def stale_session_for(session_id: str | None) -> bool:
    """True if a session exists but was issued on a previous IST day."""
    sess = _sessions.get(session_id or "")
    if sess is None:
        return False
    return not session_is_today(sess)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        ts = value
    elif value:
        raw = str(value).strip()
        try:
            # Kite usually gives us datetime objects, but some SDK / serialized
            # paths surface strings instead. `Z` is common in JSON payloads and
            # older Python builds do not always accept it directly.
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            # Never leak a broker-specific raw string to the frontend: a single
            # malformed value becomes "Invalid Date" in the recent-trades card.
            logger.warning("[kite] Unparseable trade timestamp %r; using current UTC time", value)
            ts = datetime.now(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def kite_margins_to_finsight(raw_margins: dict[str, Any]) -> dict[str, Any]:
    equity = (raw_margins or {}).get("equity", {}) or {}
    available = equity.get("available", {}) or {}
    utilised = equity.get("utilised", {}) or {}

    available_cash = _to_float(available.get("live_balance", available.get("cash", 0)))
    opening_balance = _to_float(available.get("opening_balance", 0))
    utilised_debits = _to_float(utilised.get("debits", 0))
    utilised_m2m = _to_float(
        utilised.get("m2m_realised", utilised.get("m2m", utilised.get("pnl", 0)))
    )
    total = available_cash + utilised_debits
    if total <= 0:
        total = max(opening_balance + utilised_debits, PAPER_CAPITAL)

    return {
        "available_cash": available_cash,
        "opening_balance": opening_balance,
        "utilised_debits": utilised_debits,
        "utilised_m2m": utilised_m2m,
        "available": max(0.0, available_cash),
        "used": max(0.0, utilised_debits),
        "total": max(total, 1.0),
        "raw": raw_margins,
    }


def kite_holdings_to_finsight(raw_holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw_holdings or []:
        qty = int(row.get("quantity", 0) or 0)
        avg = _to_float(row.get("average_price", 0))
        ltp = _to_float(row.get("last_price", 0))
        pnl = _to_float(row.get("pnl", (ltp - avg) * qty))
        exposure_price = ltp if ltp > 0 else avg
        out.append({
            "symbol": row.get("tradingsymbol", ""),
            "exchange": row.get("exchange", "NSE"),
            "quantity": qty,
            "avg_price": avg,
            "ltp": ltp,
            "pnl": pnl,
            "day_change_pct": _to_float(row.get("day_change_percentage", 0)),
            "exposure": abs(qty) * exposure_price,
        })
    return out


def kite_positions_to_finsight(raw_positions: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in (raw_positions or {}).get("net", []) or []:
        qty = int(row.get("quantity", 0) or 0)
        if qty == 0:
            continue
        avg = _to_float(row.get("average_price", 0))
        exposure = abs(qty) * avg
        out.append({
            "symbol": row.get("tradingsymbol", ""),
            "exchange": row.get("exchange", "NSE"),
            "product": row.get("product", ""),
            "side": "BUY" if qty > 0 else "SELL",
            "quantity": abs(qty),
            "avg_price": avg,
            "pnl": _to_float(row.get("pnl", row.get("m2m", 0))),
            "m2m": _to_float(row.get("m2m", row.get("pnl", 0))),
            "last_price": _to_float(row.get("last_price", 0)),
            "exposure": exposure,
        })
    return out


def _match_trade_book(raw_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trades_sorted = sorted(
        raw_trades or [],
        key=lambda t: (
            str(t.get("trade_timestamp") or t.get("order_timestamp") or ""),
            str(t.get("trade_id") or t.get("order_id") or ""),
        ),
    )

    open_lots: dict[str, list[dict[str, Any]]] = {}
    out: list[dict[str, Any]] = []

    for trade in trades_sorted:
        symbol = str(trade.get("tradingsymbol", ""))
        action = str(trade.get("transaction_type", "BUY")).upper()
        quantity = int(trade.get("quantity", 0) or 0)
        price = _to_float(trade.get("average_price", trade.get("price", 0)))
        remaining = quantity
        realized_pnl = 0.0
        matched = 0

        lots = open_lots.setdefault(symbol, [])
        while remaining > 0 and lots and lots[0]["side"] != action:
            lot = lots[0]
            take = min(remaining, lot["quantity"])
            if lot["side"] == "BUY":
                lot_pnl = (price - lot["price"]) * take
            else:
                lot_pnl = (lot["price"] - price) * take
            realized_pnl += lot_pnl
            matched += take
            remaining -= take
            lot["quantity"] -= take
            if lot["quantity"] == 0:
                lots.pop(0)

        if remaining > 0:
            lots.append({"side": action, "quantity": remaining, "price": price})

        timestamp = trade.get("trade_timestamp") or trade.get("order_timestamp") or datetime.now(timezone.utc)
        out.append({
            "trade_id": trade.get("trade_id") or trade.get("order_id") or "",
            "order_id": trade.get("trade_id") or trade.get("order_id") or "",
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "timestamp": _to_iso(timestamp),
            "quantity_remaining": remaining if matched == 0 else 0,
            "realized_pnl": round(realized_pnl, 2) if matched else None,
            "is_loss": (realized_pnl < 0) if matched else None,
        })

    return out


def kite_trades_to_finsight(kite_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _match_trade_book(kite_trades)


def _derive_watchlist_instruments(
    positions: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    symbols: list[str] | None = None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(sym: str) -> None:
        sym = sym.strip()
        if not sym:
            return
        inst = sym if ":" in sym else f"NSE:{sym}"
        if inst not in seen:
            ordered.append(inst)
            seen.add(inst)

    for sym in symbols or []:
        add(sym)

    for pos in positions:
        add(pos.get("symbol", ""))

    for holding in holdings:
        add(holding.get("symbol", ""))

    for sym in DEFAULT_WATCHLIST:
        add(sym)

    return ordered[:5]


def kite_watchlist_to_finsight(
    raw_quotes: dict[str, Any],
    instruments: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for symbol in instruments:
        payload = (raw_quotes or {}).get(symbol)
        if not isinstance(payload, dict):
            continue
        ohlc = payload.get("ohlc", {}) or {}
        last = _to_float(payload.get("last_price", 0))
        close = _to_float(ohlc.get("close", last), last)
        change = last - close
        change_pct = (change / close * 100) if close else 0.0
        out.append({
            "symbol": symbol,
            "last_price": last,
            "open": _to_float(ohlc.get("open", 0)),
            "high": _to_float(ohlc.get("high", 0)),
            "low": _to_float(ohlc.get("low", 0)),
            "close": close,
            "change": change,
            "change_pct": change_pct,
            "volume": int(payload.get("volume", 0) or 0),
        })
    return out


def _infer_loss_streak(trades: list[dict[str, Any]]) -> int:
    streak = 0
    for trade in reversed(trades):
        if trade.get("realized_pnl") is None:
            continue
        if trade.get("is_loss"):
            streak += 1
            continue
        break
    return streak


def build_account_snapshot(
    raw_margins: dict[str, Any],
    raw_holdings: list[dict[str, Any]],
    raw_positions: dict[str, Any],
    raw_trades: list[dict[str, Any]],
    raw_quotes: dict[str, Any],
    *,
    watchlist_instruments: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    margins = kite_margins_to_finsight(raw_margins)
    holdings = kite_holdings_to_finsight(raw_holdings)
    positions = kite_positions_to_finsight(raw_positions)
    trades = kite_trades_to_finsight(raw_trades)
    watchlist = kite_watchlist_to_finsight(raw_quotes, watchlist_instruments)

    closed_trades = [t for t in trades if t.get("realized_pnl") is not None]
    derived_realized_pnl = round(sum(_to_float(t.get("realized_pnl")) for t in closed_trades), 2)
    loss_count = sum(1 for t in closed_trades if t.get("is_loss"))
    open_pnl = round(sum(_to_float(pos.get("pnl")) for pos in positions), 2)

    broker_realized = _to_float(margins.get("utilised_m2m"), 0.0)
    if closed_trades:
        realized_pnl = derived_realized_pnl
        realized_pnl_source = "derived"
    elif broker_realized != 0.0:
        realized_pnl = round(broker_realized, 2)
        realized_pnl_source = "exact"
    else:
        realized_pnl = 0.0
        realized_pnl_source = "unknown"

    exposures = [
        _to_float(item.get("exposure"))
        for item in [*positions, *holdings]
        if _to_float(item.get("exposure")) > 0
    ]
    total_exposure = round(sum(exposures), 2)
    concentration = (max(exposures) / total_exposure) if total_exposure > 0 else 0.0

    summary = {
        "since": "today",
        "total_trades": len(trades),
        "closed_trades": len(closed_trades),
        "realized_pnl": realized_pnl,
        "realized_pnl_source": realized_pnl_source,
        "loss_count": loss_count,
        "open_pnl": open_pnl,
        "open_pnl_source": "exact" if positions else "unknown",
        "open_positions_count": len(positions),
        "holdings_count": len(holdings),
        "net_day_pnl": round(realized_pnl + open_pnl, 2),
        "available_cash": margins["available_cash"],
        "utilised_margin": margins["utilised_debits"],
        "total_exposure": total_exposure,
        "exposure_concentration": concentration,
        "inferred_loss_streak": _infer_loss_streak(trades),
    }

    return {
        "margins": {
            "available_cash": margins["available_cash"],
            "opening_balance": margins["opening_balance"],
            "utilised_debits": margins["utilised_debits"],
            "utilised_m2m": margins["utilised_m2m"],
            "available": margins["available"],
            "used": margins["used"],
            "total": margins["total"],
        },
        "holdings": holdings,
        "positions": positions,
        "trades": trades,
        "watchlist": watchlist,
        "watchlist_symbols": watchlist_instruments,
        "summary": summary,
        "warnings": warnings or [],
        "raw": {
            "margins": raw_margins,
            "holdings": raw_holdings,
            "positions": raw_positions,
            "trades": raw_trades,
        },
    }


def _coerce_snapshot_piece(
    label: str,
    result: Any,
    default: Any,
    warnings: list[str],
) -> Any:
    if isinstance(result, PermissionError):
        raise result
    if isinstance(result, Exception):
        msg = str(result)
        # Suppress two classes of noise from the user-visible Broker Notes:
        #   1. "Insufficient permission for that call" — user's Kite Connect
        #      plan doesn't include that endpoint (e.g., /quote on the free
        #      Personal tier). The feature degrades gracefully on its own.
        #   2. DNS / network errors — the daily-reauth banner already
        #      surfaces a top-level "Reconnect Kite" CTA; piling 5 stack
        #      traces into Broker Notes adds nothing.
        suppress = (
            "Insufficient permission" in msg
            or "Max retries exceeded" in msg
            or "NameResolutionError" in msg
            or "getaddrinfo failed" in msg
        )
        if not suppress:
            warnings.append(f"{label} unavailable: {msg}")
        return default
    return result


async def get_account_snapshot(
    session_id: str,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    margins_res, holdings_res, positions_res, trades_res = await asyncio.gather(
        get_margins(session_id),
        get_holdings(session_id),
        get_positions(session_id),
        get_trades(session_id),
        return_exceptions=True,
    )

    raw_margins = _coerce_snapshot_piece("margins", margins_res, {}, warnings)
    raw_holdings = _coerce_snapshot_piece("holdings", holdings_res, [], warnings)
    raw_positions = _coerce_snapshot_piece("positions", positions_res, {}, warnings)
    raw_trades = _coerce_snapshot_piece("trades", trades_res, [], warnings)

    holdings = kite_holdings_to_finsight(raw_holdings)
    positions = kite_positions_to_finsight(raw_positions)
    instruments = _derive_watchlist_instruments(positions, holdings, symbols=symbols)

    quotes_res = await asyncio.gather(
        get_quote(session_id, instruments),
        return_exceptions=True,
    )
    raw_quotes = _coerce_snapshot_piece("watchlist", quotes_res[0], {}, warnings)

    return build_account_snapshot(
        raw_margins,
        raw_holdings,
        raw_positions,
        raw_trades,
        raw_quotes,
        watchlist_instruments=instruments,
        warnings=warnings,
    )
