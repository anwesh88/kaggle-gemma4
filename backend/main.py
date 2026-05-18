import os, time, asyncio, json
from contextlib import asynccontextmanager
from urllib.parse import urlencode
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import base64

load_dotenv()
from models import TradingContext, BehavioralAnalysis, TradeRequest, VowsUpdate, Language
from broker_client import get_trading_context, get_kite_trading_context
from ai_engine import (
    analyze_behavior, get_unavailable_analysis, warm_up_model, OLLAMA_MODEL,
    analyze_behavior_stream,
)
from behavioral_dna import get_behavioral_dna, save_session, get_historical_context
from multimodal_engine import analyze_chart_image, analyze_chart_full
from rag_engine import retrieve_sebi_context
from market_data import get_market_snapshot
from paper_trading import (
    record_trade as paper_record_trade,
    get_recent_trades as paper_get_recent_trades,
    get_open_positions as paper_get_open_positions,
    get_session_pnl as paper_get_session_pnl,
    reset_db as paper_reset_db,
)
import kite_client


# ── Mode-aware dispatch ──────────────────────────────────────────────────────
# The frontend threads the user's chosen mode into every request via the
# X-Finsight-Mode header. Three values: "demo" | "paper" | "kite". Most
# endpoints behave identically across demo and paper (paper just lets the
# user place real fresh trades). The "kite" path routes reads/writes to the
# Live Kite Connect adapter.

VALID_MODES = {"demo", "paper", "kite"}
KITE_COOKIE = "finsight_kite_session"

def get_mode(request: Request) -> str:
    m = (request.headers.get("X-Finsight-Mode", "") or "").lower()
    return m if m in VALID_MODES else "demo"

def get_kite_session(request: Request) -> str | None:
    return request.cookies.get(KITE_COOKIE)

def dna_mode_for(mode: str) -> str:
    return mode if mode in VALID_MODES else "demo"

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
user_vows: list[str] = [
    "I will stop trading after 2 consecutive losses",
    "I will not use more than 50% of my margin",
    "I will not revenge trade after a big loss",
]
preferred_language = Language.EN


def get_cors_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for value in (
            os.getenv("FRONTEND_URL", "http://localhost:3000"),
            os.getenv("FRONTEND_ORIGINS", ""),
        )
        for origin in value.split(",")
        if origin.strip()
    ]
    local_defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    return list(dict.fromkeys(configured + local_defaults))

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n Finsight OS - Behavioral Guardian for India's Retail Traders")
    print(f"   Mode: {'DEMO (Seeded high-risk session)' if DEMO_MODE else 'LIVE (Zerodha Kite)'}")
    print(f"   AI:   {OLLAMA_MODEL} via Ollama (local, private, CPU)")
    print(f"   RAG:  Initializing SEBI circular index...")
    from rag_engine import get_collection
    get_collection()
    print(f"   RAG:  SEBI circulars indexed")

    # Pre-warm Gemma so the first user request doesn't pay cold-start.
    # Runs in the background — we don't block startup if Ollama is offline.
    asyncio.create_task(warm_up_model())

    # Restore the last Kite session from encrypted disk (if any). Single
    # profile() call; cheap. If the daily 6 AM IST expiry has fired, this
    # silently no-ops and the user re-OAuths from the UI.
    try:
        restored = kite_client.restore_session_from_disk()
        if restored:
            print(f"   Kite: Restored session for {restored.user_name}")
        diag = kite_client.redirect_diagnostics()
        if diag.get("warning"):
            print(f"   Kite: {diag['warning']}")
    except Exception as e:
        print(f"   Kite: restore skipped ({e})")

    yield

app = FastAPI(title="Finsight OS API", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=os.getenv(
        "FRONTEND_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    ),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health(request: Request):
    """
    Server status + Kite session state. Frontend uses this to decide
    whether to show "Connected as <name>" pill in Live Kite mode.
    """
    sid = get_kite_session(request)
    kite_state = kite_client.status_dict(
        sid or kite_client.PERSISTED_SESSION_ID,
        cookie_present=bool(sid),
        request_base_url=str(request.base_url),
    ) if sid or kite_client.is_configured() else {
        "configured": False, "authenticated": False
    }
    return {
        "status": "ok",
        "demo_mode": DEMO_MODE,
        "model": OLLAMA_MODEL,
        "edge_ai": True,
        "kite": kite_state,
    }


@app.post("/analyze-behavior", response_model=BehavioralAnalysis)
async def analyze(request: Request):
    mode = get_mode(request)

    # Read raw body. If empty or missing fields, build the real mode-scoped
    # trading context from SQLite paper trades or the live Kite snapshot.
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Only parse as TradingContext if the body has the required fields
    if body and "recent_trades" in body and "margin" in body:
        ctx = TradingContext(**body)
    else:
        # Live Kite path: pull real trades + margin from Zerodha
        if mode == "kite":
            sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
            if kite_client.is_authenticated(sid):
                try:
                    ctx = await get_kite_trading_context(sid)
                except Exception as e:
                    print(f"[analyze/kite] live fetch failed: {e} — falling back to paper context")
                    ctx = get_trading_context(mode="paper")
            else:
                ctx = get_trading_context(mode="paper")
        else:
            ctx = get_trading_context(mode=mode)

    ctx.trading_vows = user_vows
    ctx.preferred_language = preferred_language

    # Enrich with historical context (mode-scoped — paper users start fresh)
    dna_mode = dna_mode_for(mode)
    hist_sessions, hist_loss_rate = get_historical_context(mode=dna_mode)
    ctx.historical_sessions = hist_sessions
    ctx.historical_loss_rate = hist_loss_rate

    # Enrich SEBI disclosure via RAG
    loss_count = len([t for t in ctx.recent_trades if t.is_loss])
    sebi_ctx, sebi_source = retrieve_sebi_context(
        f"retail F&O trading {loss_count} losses margin {ctx.margin.usage_ratio*100:.0f}%"
    )

    # Run Gemma 4 analysis. If Ollama fails, show an explicit unavailable
    # state instead of invented behavioral insight.
    try:
        result = await analyze_behavior(ctx)
    except Exception as e:
        print(f"[ERROR] Gemma failed: {e} - no model insight produced")
        result = get_unavailable_analysis(ctx, f"Server error: {type(e).__name__}: {e}")

    model_completed = result.inference_seconds is not None
    if model_completed:
        # Attach RAG-grounded SEBI disclosure only to completed model output.
        result.sebi_disclosure = sebi_ctx[:200]
        result.sebi_source = sebi_source

    # Persist session to Behavioral DNA (skipped for empty paper-mode runs
    # by save_session itself — see behavioral_dna.save_session for the gate).
    if model_completed:
        session_id = f"S{int(time.time())}"
        activity_count = (
            max(len(ctx.recent_trades), ctx.open_positions_count, ctx.holdings_count)
            if mode == "kite"
            else len(ctx.recent_trades)
        )
        save_session(
            session_id,
            result,
            activity_count,
            ctx.margin.usage_ratio * 100,
            mode=dna_mode,
        )

    return result


@app.get("/behavioral-dna")
async def get_dna(request: Request):
    mode = get_mode(request)
    dna_mode = dna_mode_for(mode)
    return get_behavioral_dna(mode=dna_mode)


@app.post("/analyze-chart")
async def analyze_chart(request: Request, file: UploadFile = File(...)):
    """
    Four-layer behavioral chart analysis. Reads the user's behavioral DNA +
    recent trades for the current mode and feeds them to the vision model so
    the output is personalized ("This setup resembles your previous FOMO
    trades") instead of generic technical-indicator commentary.
    """
    contents = await file.read()
    b64 = base64.b64encode(contents).decode()
    mode = get_mode(request)

    # Build trader context for the personalized-insight layer. Best-effort:
    # if any of these calls fail (paper DB empty, Kite session stale), we
    # pass a partial context and the model handles the missing fields.
    trader_context: dict = {}
    try:
        dna_mode = dna_mode_for(mode)
        trader_context["dna"] = get_behavioral_dna(mode=dna_mode)
    except Exception as e:
        print(f"[analyze-chart] DNA fetch failed: {e}")

    try:
        if mode == "kite":
            sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
            if kite_client.is_authenticated(sid):
                ctx = await get_kite_trading_context(sid)
            else:
                ctx = get_trading_context(mode="paper")
        else:
            ctx = get_trading_context(mode=mode)
        trader_context["recent_trades"] = [
            {"symbol": t.symbol, "action": t.action, "quantity": t.quantity,
             "price": t.price, "pnl": t.pnl, "is_loss": getattr(t, "is_loss", False)}
            for t in (ctx.recent_trades or [])[:10]
        ]
        trader_context["margin_usage_pct"] = round(ctx.margin.usage_ratio * 100)
        # Compute active loss streak from the tail of the trade list
        streak = 0
        for t in reversed(ctx.recent_trades or []):
            if getattr(t, "pnl", None) is None:
                continue
            if getattr(t, "is_loss", False):
                streak += 1
            else:
                break
        trader_context["loss_streak"] = streak
    except Exception as e:
        print(f"[analyze-chart] Trading context fetch failed: {e}")

    full = await analyze_chart_full(
        b64,
        symbol=file.filename or "",
        context=trader_context or None,
    )

    # Attach deterministic reasons for any 0% behavioral-risk score. The
    # model is honest about low risk in calm conditions / empty history,
    # but a bare 0% bar reads as "broken" in the UI. These rationales tell
    # the user *why* the score is 0 (no history yet, sideways chart, etc.)
    risk = full.get("behavioral_risk") or {}
    structure = full.get("market_structure") or {}
    has_history    = bool((trader_context.get("dna") or {}).get("total_sessions"))
    recent_trades  = trader_context.get("recent_trades") or []
    loss_streak    = int(trader_context.get("loss_streak") or 0)
    win_count      = sum(1 for t in recent_trades if t.get("pnl") is not None and not t.get("is_loss"))
    trend          = (structure.get("trend") or "").lower()
    momentum       = (structure.get("momentum") or "").lower()
    volatility     = (structure.get("volatility") or "").lower()
    market_state   = (full.get("market_state") or "").lower()

    def _reason(key: str, score: int) -> str | None:
        if score > 0:
            return None
        if key == "fomo_probability":
            if market_state == "ranging" or trend == "sideways":
                return "Sideways/ranging chart — no breakout to chase."
            if momentum in ("weakening", "exhausted"):
                return "Momentum is fading, not the late-rally pattern FOMO requires."
            if not has_history:
                return "No prior FOMO entries logged yet — score is baseline."
            return "No late-entry chasing pattern visible on this chart."
        if key == "revenge_probability":
            if loss_streak == 0 and not has_history:
                return "No recent losses logged — nothing to 'revenge' against."
            if loss_streak == 0:
                return "Your last trade wasn't a loss, so no revenge trigger."
            return "Loss streak is short and chart isn't a recovery setup."
        if key == "panic_probability":
            if volatility in ("low", "normal") and trend != "down":
                return "Volatility is normal and price isn't crashing — no capitulation signals."
            if trend == "sideways":
                return "Sideways price action rules out capitulation."
            return "Chart doesn't show the sharp drop or long lower wicks that drive panic exits."
        if key == "overconfidence_risk":
            if win_count == 0 and not has_history:
                return "No winning streak logged — overconfidence needs prior wins to anchor on."
            if win_count <= 1:
                return "Win count too low to inflate position-sizing confidence."
            return "Recent wins exist but chart doesn't invite oversizing here."
        return "No risk signal detected on this dimension."

    risk_reasons: dict[str, str] = {}
    for k in ("fomo_probability", "revenge_probability", "panic_probability", "overconfidence_risk"):
        try:
            score = int(risk.get(k, 0) or 0)
        except (TypeError, ValueError):
            score = 0
        reason = _reason(k, score)
        if reason:
            risk_reasons[k] = reason

    if isinstance(full.get("behavioral_risk"), dict):
        full["behavioral_risk"]["reasons"] = risk_reasons
    else:
        full["behavioral_risk"] = {"reasons": risk_reasons}

    return {
        # Legacy field kept for any older UI surface that read .insight directly.
        "insight":               full.get("personalized_insight") or full.get("behavioral_warning"),
        "market_state":          full.get("market_state"),
        "market_structure":      full.get("market_structure"),
        "behavioral_risk":       full.get("behavioral_risk"),
        "decision_quality":      full.get("decision_quality"),
        "personalized_insight":  full.get("personalized_insight"),
        "behavioral_warning":    full.get("behavioral_warning"),
        "error":                 full.get("error"),
    }


@app.post("/trading-vows")
async def update_vows(update: VowsUpdate):
    global user_vows, preferred_language
    user_vows = update.vows
    preferred_language = update.preferred_language
    return {"status": "saved", "count": len(user_vows)}

@app.get("/trading-vows")
async def get_vows():
    return {"vows": user_vows, "language": preferred_language}

@app.get("/quotes/lookup")
async def quotes_lookup(symbols: str = ""):
    """
    Look up LTP + day-change for arbitrary NSE symbols using yfinance.

    Used by the in-app watchlist (Kite Personal plan doesn't include
    /quote API access, so we fall back to Yahoo Finance which is free).
    Pass `?symbols=ETERNAL,SUZLON,KRONOX` — `.NS` suffixes are added
    automatically.
    """
    raw = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not raw:
        return {"quotes": [], "count": 0}

    # Run the same _fetch_yahoo_sync helper market_data already uses so we
    # benefit from its _dividends bug guard + history-fallback retry.
    from market_data import _fetch_yahoo
    yahoo_syms = [s if "." in s else f"{s}.NS" for s in raw]

    try:
        rows = await _fetch_yahoo(yahoo_syms)
    except Exception as e:
        # Yahoo down → return zeros so the UI still renders the symbol rows.
        print(f"[quotes/lookup] yfinance failed: {e}")
        rows = []

    by_sym = {r["symbol"]: r for r in rows}
    out = []
    for sym, ysym in zip(raw, yahoo_syms):
        r = by_sym.get(ysym)
        if r is None:
            out.append({"symbol": sym, "last_price": 0.0, "prev_close": 0.0,
                        "change": 0.0, "change_pct": 0.0, "available": False})
            continue
        last = float(r.get("regularMarketPrice", 0) or 0)
        prev = float(r.get("regularMarketPreviousClose", last) or last)
        change = last - prev
        pct = (change / prev * 100) if prev else 0.0
        out.append({
            "symbol":     sym,
            "last_price": last,
            "prev_close": prev,
            "change":     change,
            "change_pct": pct,
            "available":  True,
        })
    return {"quotes": out, "count": len(out)}


@app.get("/market-quotes")
async def market_quotes():
    """Live NSE watchlist quotes (Yahoo Finance, 30s server-side cache)."""
    snap = await get_market_snapshot()
    return snap.to_dict()


@app.post("/analyze-behavior-stream")
async def analyze_stream(request: Request):
    """
    Server-Sent Events variant of /analyze-behavior.

    Streams the audited analysis trace token-by-token to the UI as it's produced.
    Each event is a JSON object with one of:
        {"type": "status",  "message": str}
        {"type": "token",   "text":    str}
        {"type": "result",  "analysis": BehavioralAnalysis dict}

    The same broker_client / RAG enrichment / behavioral DNA persistence
    happens here as in /analyze-behavior — only the model output streams.
    """
    mode = get_mode(request)
    try:
        body = await request.json()
    except Exception:
        body = {}

    if body and "recent_trades" in body and "margin" in body:
        ctx = TradingContext(**body)
    else:
        if mode == "kite":
            sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
            if kite_client.is_authenticated(sid):
                try:
                    ctx = await get_kite_trading_context(sid)
                except Exception as e:
                    print(f"[stream/kite] live fetch failed: {e} — falling back to paper context")
                    ctx = get_trading_context(mode="paper")
            else:
                ctx = get_trading_context(mode="paper")
        else:
            ctx = get_trading_context(mode=mode)

    ctx.trading_vows = user_vows
    ctx.preferred_language = preferred_language

    # Mode-scoped historical context (paper users start fresh, demo carries
    # the canonical 30-session high-risk history)
    dna_mode = "demo" if mode == "demo" else "paper"
    hist_sessions, hist_loss_rate = get_historical_context(mode=dna_mode)
    ctx.historical_sessions = hist_sessions
    ctx.historical_loss_rate = hist_loss_rate

    # SEBI RAG retrieval up front so we can attach it to the final result
    loss_count = len([t for t in ctx.recent_trades if t.is_loss])
    sebi_ctx, sebi_source = retrieve_sebi_context(
        f"retail F&O trading {loss_count} losses margin {ctx.margin.usage_ratio*100:.0f}%"
    )

    async def event_stream():
        async for event in analyze_behavior_stream(ctx):
            # Attach SEBI grounding + persist session at the result event
            if event.get("type") == "result":
                analysis_dict = event["analysis"]
                model_completed = analysis_dict.get("inference_seconds") is not None
                if model_completed:
                    analysis_dict["sebi_disclosure"] = sebi_ctx[:200]
                    analysis_dict["sebi_source"] = sebi_source

                if model_completed:
                    try:
                        session_id = f"S{int(time.time())}"
                        activity_count = (
                            max(len(ctx.recent_trades), ctx.open_positions_count, ctx.holdings_count)
                            if mode == "kite"
                            else len(ctx.recent_trades)
                        )
                        save_session(
                            session_id,
                            BehavioralAnalysis(**analysis_dict),
                            activity_count,
                            ctx.margin.usage_ratio * 100,
                            mode=dna_mode,
                        )
                    except Exception as e:
                        print(f"[stream] save_session failed: {e}")

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Explicit close marker so the client can release resources cleanly.
        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@app.post("/confirm-trade")
async def confirm_trade(trade: TradeRequest, request: Request):
    """
    Persist or place a trade. Mode-aware:
      - demo / paper → SQLite paper-trading engine (FIFO matched)
      - kite         → real broker via kiteconnect (real money)
    """
    mode = get_mode(request)
    print(f"[TRADE/{mode}] {trade.action} {trade.quantity}x {trade.symbol} @ Rs.{trade.price}")

    if mode == "kite":
        sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
        if not sid or not kite_client.is_authenticated(sid):
            raise HTTPException(status_code=401, detail="Not logged in to Kite — re-login required.")
        try:
            result = await kite_client.place_order(
                sid, trade.symbol, trade.quantity, trade.price, trade.action,
            )
            return {"status": "confirmed", "order_id": result.get("order_id", ""), "broker": "kite"}
        except PermissionError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Kite error: {e}")

    # demo / paper paths use mode-specific SQLite (paper_trading_demo.db
    # vs paper_trading_user.db) — set in paper_trading._db_path(mode).
    try:
        result = paper_record_trade(
            symbol=trade.symbol, action=trade.action,
            quantity=trade.quantity, price=trade.price,
            mode=mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "confirmed", **result, "broker": "paper", "mode": mode}


@app.get("/trade-history")
async def trade_history(request: Request, limit: int = 20):
    """Recent trades. Mode-aware: paper trades from SQLite OR Kite trades from broker."""
    mode = get_mode(request)
    if mode == "kite":
        sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
        if sid and kite_client.is_authenticated(sid):
            try:
                snapshot = await kite_client.get_account_snapshot(sid)
                return {
                    "trades": snapshot.get("trades", [])[:limit],
                    "session_pnl": {
                        "since": snapshot.get("summary", {}).get("since", "today"),
                        "total_trades": snapshot.get("summary", {}).get("total_trades", 0),
                        "closed_trades": snapshot.get("summary", {}).get("closed_trades", 0),
                        "realized_pnl": snapshot.get("summary", {}).get("realized_pnl", 0.0),
                        "loss_count": snapshot.get("summary", {}).get("loss_count", 0),
                    },
                    "mode": "kite",
                }
            except PermissionError as e:
                raise HTTPException(status_code=401, detail=str(e))
            except Exception as e:
                print(f"[trade-history/kite] {e} — falling back to paper view")

    return {
        "trades": paper_get_recent_trades(limit=limit, mode=mode),
        "session_pnl": paper_get_session_pnl(mode=mode),
        "mode": mode,
    }


@app.get("/portfolio")
async def portfolio(request: Request):
    """Open positions. Mode-aware: paper SQLite OR Kite positions['net']."""
    mode = get_mode(request)
    if mode == "kite":
        sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
        if sid and kite_client.is_authenticated(sid):
            try:
                snapshot = await kite_client.get_account_snapshot(sid)
                return {
                    "positions": snapshot.get("positions", []),
                    "session_pnl": {
                        "since": snapshot.get("summary", {}).get("since", "today"),
                        "total_trades": snapshot.get("summary", {}).get("total_trades", 0),
                        "closed_trades": snapshot.get("summary", {}).get("closed_trades", 0),
                        "realized_pnl": snapshot.get("summary", {}).get("realized_pnl", 0.0),
                        "loss_count": snapshot.get("summary", {}).get("loss_count", 0),
                    },
                    "mode": "kite",
                }
            except PermissionError as e:
                raise HTTPException(status_code=401, detail=str(e))
            except Exception as e:
                print(f"[portfolio/kite] {e} — falling back to paper view")

    return {
        "positions": paper_get_open_positions(mode=mode),
        "session_pnl": paper_get_session_pnl(mode=mode),
        "mode": mode,
    }


@app.post("/paper/reset")
async def paper_reset(request: Request):
    """
    Wipe the paper-trading SQLite for the current mode and re-init empty.
    Only honored when mode=paper. Demo mode auto-seeds on next analysis,
    so wiping it would just trigger another seed — refused for safety.
    """
    mode = get_mode(request)
    if mode != "paper":
        raise HTTPException(
            status_code=400,
            detail=f"Reset only available in Paper Trading mode (current: {mode}).",
        )
    result = paper_reset_db(mode="paper")
    return {"ok": True, **result}


# ── Live Kite Connect routes ─────────────────────────────────────────────────

@app.get("/kite/status")
async def kite_status(request: Request):
    """
    Tells the frontend whether Kite is configured + the user is logged in.
    Falls back to the persisted-disk session id when no cookie is present
    (auto-login after backend restart).
    """
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    return kite_client.status_dict(
        sid,
        cookie_present=bool(get_kite_session(request)),
        request_base_url=str(request.base_url),
    )


@app.get("/kite/login-url")
async def kite_login_url():
    """Returns the Zerodha OAuth login URL the frontend opens for the user."""
    if not kite_client.is_configured():
        raise HTTPException(status_code=503,
            detail="Kite Connect is not configured. Set KITE_API_KEY and KITE_API_SECRET in backend/.env.")
    return {"login_url": kite_client.login_url()}


@app.get("/kite/callback")
async def kite_callback(request_token: str = "", status: str = "", action: str = ""):
    """
    Zerodha redirects here after the user logs in. We exchange the
    request_token for an access_token, set a server-side session, drop the
    session id into an HTTP-only cookie, and redirect back to the dashboard.
    """
    if not kite_client.is_configured():
        raise HTTPException(status_code=503, detail="Kite Connect not configured")
    if status != "success" or not request_token:
        raise HTTPException(status_code=400, detail=f"Kite login failed: status={status!r}")

    try:
        sid, _sess = kite_client.handle_callback(request_token, source="cookie")
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))

    front = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    redirect_url = f"{front}/kite/callback?{urlencode({'status': 'connected'})}"
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key=KITE_COOKIE, value=sid,
        httponly=True, samesite="lax", path="/",
        max_age=60 * 60 * 12,                      # Kite tokens expire ~6 AM IST → 12h is safe
    )
    return response


class ManualKiteLogin(BaseModel):
    # Accepts either a bare request_token or the full URL the browser landed on
    # after the (possibly broken) redirect, e.g.
    #   https://127.0.0.1/?action=login&type=login&status=success&request_token=ABC...
    request_token_or_url: str


@app.post("/kite/manual-callback")
async def kite_manual_callback(body: ManualKiteLogin):
    """
    Paste-flow login. Use this when Zerodha's redirect URL in your developer
    console points somewhere we can't catch (e.g., https://127.0.0.1/ with no
    backend on port 443). The frontend prompts the user to copy the URL bar
    after the broken redirect, paste it here, and we extract the request_token
    and exchange it the same way /kite/callback does.
    """
    if not kite_client.is_configured():
        raise HTTPException(status_code=503, detail="Kite Connect not configured")

    rt = kite_client.extract_request_token(body.request_token_or_url)
    if not rt:
        raise HTTPException(
            status_code=400,
            detail="No request_token found. Paste either the bare token or the full URL "
                   "from your browser bar (the one that contains '?request_token=...').",
        )

    try:
        sid, sess = kite_client.handle_callback(rt, source="manual_fallback")
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))

    response = JSONResponse(content={
        "ok":         True,
        "user_id":    sess.user_id,
        "user_name":  sess.user_name,
    })
    response.set_cookie(
        key=KITE_COOKIE, value=sid,
        httponly=True, samesite="lax", path="/",
        max_age=60 * 60 * 12,
    )
    return response


@app.get("/kite/instruments/search")
async def kite_instruments_search(request: Request, q: str = "", limit: int = 12):
    """
    Fuzzy stock search over the cached Kite NSE instruments list. Returns
    a small dropdown-ready slice with tradingsymbol, exchange, name, and
    instrument_token (the latter for the trade panel to attach internally).
    """
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")
    if not q.strip():
        return {"matches": []}
    try:
        matches = await kite_client.search_instruments(sid, q, limit=limit)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"matches": matches, "count": len(matches)}


class PlaceOrderBody(BaseModel):
    symbol: str
    quantity: int
    transaction_type: str = "BUY"   # BUY | SELL
    product: str = "MIS"            # MIS (intraday) | CNC (delivery)
    order_type: str = "MARKET"      # MARKET | LIMIT
    price: float | None = None      # required iff order_type == "LIMIT"
    exchange: str = "NSE"


@app.post("/kite/place-order")
async def kite_place_order(request: Request, body: PlaceOrderBody):
    """
    Place a REAL order on the user's Zerodha account. The Mindful Speed Bump
    must already have been satisfied by the frontend — this endpoint trusts
    that the request only fires post-confirmation.

    Daily re-auth gate: rejects with 401 if the user's session is from a
    previous IST day, prompting the frontend to re-trigger login.
    """
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")
    if kite_client.stale_session_for(sid):
        raise HTTPException(
            status_code=401,
            detail="Your Kite session is from a previous trading day. Please re-login to continue.",
        )

    tx = body.transaction_type.upper()
    if tx not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="transaction_type must be BUY or SELL")
    ot = body.order_type.upper()
    if ot not in {"MARKET", "LIMIT"}:
        raise HTTPException(status_code=400, detail="order_type must be MARKET or LIMIT")
    if ot == "LIMIT" and (body.price is None or body.price <= 0):
        raise HTTPException(status_code=400, detail="LIMIT orders require a positive price")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0")

    try:
        result = await kite_client.place_order(
            session_id       = sid,
            symbol           = body.symbol.upper(),
            quantity         = body.quantity,
            price            = body.price or 0.0,
            transaction_type = tx,
            exchange         = body.exchange.upper(),
            product          = body.product.upper(),
            order_type       = ot,
        )
    except PermissionError as e:
        # Daily expiry mid-trade — surface explicitly so the UI can re-login
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        # Insufficient funds, RMS rejection, bad symbol, market closed, etc.
        # Kite returns specific exception types; we map the common ones to
        # actionable hints so the user can fix the order without a stack trace.
        err_type = type(e).__name__
        err_msg  = str(e) or err_type
        print(
            f"[kite/place-order] REJECTED · symbol={body.symbol} qty={body.quantity} "
            f"type={tx}/{ot} product={body.product} price={body.price} → "
            f"{err_type}: {err_msg}"
        )

        # Friendly rewrites for the common Kite RMS error messages
        low = err_msg.lower()
        hint = err_msg
        if "no ips configured" in low or "allowed ips" in low or ("permissionexception" in err_type.lower() and "ip" in low):
            hint = (
                "Your public IP isn't whitelisted on the Kite developer console — "
                "this is required for placing real orders. "
                "(1) Open https://api.ipify.org to find your public IP. "
                "(2) Go to https://developers.kite.trade/apps → your app → "
                "Allowed IPs → paste the IP → Save. "
                "Changes take effect immediately. Note: home connections often have "
                "dynamic IPs, so you may need to re-whitelist after a router restart."
            )
        elif "insufficient" in low and "fund" in low:
            hint = (f"Insufficient funds in your Zerodha account to place this order. "
                    f"Available cash may be lower than ₹{(body.price or 0) * body.quantity:,.0f}. "
                    f"Reduce quantity, switch to a cheaper symbol, or add funds.")
        elif "market" in low and ("open" in low or "closed" in low or "hours" in low):
            hint = ("NSE is currently closed. Equity trading runs 09:15–15:30 IST "
                    "(Mon–Fri, excluding holidays). Switch to MIS during market hours "
                    "or use a LIMIT order to queue.")
        elif "rms" in low or "block" in low:
            hint = ("Your Zerodha RMS blocked this order. Common reasons: "
                    "stock under T2T/illiquid, exchange-imposed circuit, or "
                    "product type not allowed for this scrip. Try CNC delivery or a different symbol.")
        elif "invalid" in low and ("symbol" in low or "tradingsymbol" in low or "instrument" in low):
            hint = (f"`{body.symbol}` isn't a valid NSE/BSE tradingsymbol. "
                    "Make sure you picked a symbol from the search dropdown (not a typed name).")
        elif "quantity" in low or "lot" in low:
            hint = (f"Quantity {body.quantity} isn't valid for this instrument. "
                    "F&O contracts trade in fixed lot sizes — try a multiple of the lot size.")
        elif "freeze" in low:
            hint = ("Exchange freeze-quantity exceeded. Split the order into smaller chunks.")
        elif err_type in ("ConnectionError", "ReadTimeout", "NetworkException"):
            hint = ("Couldn't reach Zerodha — network blip. Wait a few seconds and retry.")

        raise HTTPException(
            status_code=400,
            detail=f"{hint} [raw: {err_type}: {err_msg}]",
        )

    return {
        "ok":               True,
        "order_id":         result.get("order_id") if isinstance(result, dict) else str(result),
        "symbol":           body.symbol.upper(),
        "transaction_type": tx,
        "quantity":         body.quantity,
        "order_type":       ot,
        "broker":           "kite",
    }


@app.get("/kite/account-snapshot")
async def kite_account_snapshot(request: Request, symbols: str = ""):
    """
    Preferred Live Kite read model for the frontend.

    Aggregates balance, holdings, positions, watchlist, trades, and summary
    into one coherent broker snapshot to avoid mixed polling moments.
    """
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")

    requested = [
        s.strip() for s in symbols.split(",")
        if s.strip()
    ] or None
    try:
        return await kite_client.get_account_snapshot(sid, symbols=requested)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.get("/kite/margins")
async def kite_margins(request: Request):
    """Live equity + commodity available cash + utilised margin from Kite."""
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")
    try:
        snapshot = await kite_client.get_account_snapshot(sid)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return snapshot.get("margins", {})


@app.get("/kite/holdings")
async def kite_holdings(request: Request):
    """Long-term equity holdings (T+2 settled)."""
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")
    try:
        snapshot = await kite_client.get_account_snapshot(sid)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    holdings = snapshot.get("holdings", [])
    return {"holdings": holdings, "count": len(holdings)}


@app.get("/kite/watchlist")
async def kite_watchlist(request: Request, symbols: str = ""):
    """
    Live quotes for an arbitrary list of symbols. Pass `?symbols=NSE:RELIANCE,NSE:INFY`
    or comma-sep without prefix (we'll add NSE: by default).
    Falls back to a default 5-symbol watchlist if nothing is passed.
    """
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    if not kite_client.is_authenticated(sid):
        raise HTTPException(status_code=401, detail="Kite session not authenticated")
    requested = [s.strip() for s in symbols.split(",") if s.strip()] or None
    try:
        snapshot = await kite_client.get_account_snapshot(sid, symbols=requested)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    watchlist = snapshot.get("watchlist", [])
    return {"watchlist": watchlist, "count": len(watchlist)}


@app.post("/kite/logout")
async def kite_logout(request: Request):
    sid = get_kite_session(request) or kite_client.PERSISTED_SESSION_ID
    kite_client.logout(sid)
    response = {"ok": True}
    res = StreamingResponse(iter([json.dumps(response)]), media_type="application/json")
    res.delete_cookie(KITE_COOKIE, path="/")
    return res

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true" if "PORT" not in os.environ else "false").lower() == "true"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
