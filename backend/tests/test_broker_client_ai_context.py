from datetime import datetime, timezone

import pytest

import ai_engine
import broker_client
import kite_client


@pytest.mark.asyncio
async def test_live_kite_open_positions_are_visible_to_gemma_context(monkeypatch):
    async def fake_snapshot(_session_id: str):
        return {
            "margins": {"available": 75_000, "used": 25_000, "total": 100_000},
            "summary": {
                "realized_pnl": 0.0,
                "realized_pnl_source": "unknown",
                "open_pnl": -300.0,
                "open_pnl_source": "exact",
                "open_positions_count": 1,
                "holdings_count": 0,
                "total_exposure": 12984.0,
                "exposure_concentration": 1.0,
                "inferred_loss_streak": 0,
            },
            "trades": [],
            "positions": [
                {
                    "symbol": "RELIANCE",
                    "side": "BUY",
                    "quantity": 10,
                    "avg_price": 1298.40,
                    "pnl": -300.0,
                }
            ],
            "holdings": [],
            "warnings": [],
        }

    monkeypatch.setattr(kite_client, "get_account_snapshot", fake_snapshot)

    ctx = await broker_client.get_kite_trading_context("session-1")

    assert ctx.source_mode == "kite"
    assert ctx.open_positions_count == 1
    assert ctx.portfolio_positions == ["BUY RELIANCE qty=10 avg=1298.4 open_pnl=-300.0"]
    assert ctx.portfolio_holdings == []
    assert ctx.total_exposure == 12984.0
    assert len(ctx.recent_trades) == 1
    assert ctx.recent_trades[0].trade_id == "OPEN-POS-RELIANCE-BUY"
    assert ctx.recent_trades[0].pnl is None

    prompt = ai_engine.build_analysis_prompt(ctx)
    thinking_log = ai_engine._build_real_thinking_log(
        ctx,
        score=300,
        risk="low",
        pattern="Healthy Trading",
        nudge="",
        nudge_loc="",
        vows_v=[],
        crisis=0,
        elapsed=9.8,
    )

    assert "Session: 1 trades (0 closed, 1 open)" in prompt
    assert "BUY RELIANCE qty=10 @ Rs.1298.40 pnl=unrealized OPEN" in prompt
    assert "Portfolio: positions BUY RELIANCE qty=10 avg=1298.4 open_pnl=-300.0" in prompt
    assert "open P&L Rs.-300" in prompt
    assert "No trades placed yet" not in thinking_log
    assert "Python checked 1 trade(s) (1 open, 0 closed)" in thinking_log


@pytest.mark.asyncio
async def test_live_kite_context_keeps_closed_trades_and_current_positions(monkeypatch):
    async def fake_snapshot(_session_id: str):
        return {
            "margins": {"available": 50_000, "used": 50_000, "total": 100_000},
            "summary": {
                "realized_pnl": -400.0,
                "realized_pnl_source": "derived",
                "open_pnl": 120.0,
                "open_pnl_source": "exact",
                "open_positions_count": 1,
                "holdings_count": 0,
                "total_exposure": 9738.0,
                "exposure_concentration": 0.75,
                "inferred_loss_streak": 1,
            },
            "trades": [
                {
                    "trade_id": "T-CLOSED",
                    "symbol": "INFY",
                    "action": "SELL",
                    "quantity": 5,
                    "price": 1400.0,
                    "timestamp": datetime(2026, 5, 10, 9, 45, tzinfo=timezone.utc).isoformat(),
                    "realized_pnl": -400.0,
                    "is_loss": True,
                },
                {
                    "trade_id": "T-OPEN-STALE",
                    "symbol": "RELIANCE",
                    "action": "BUY",
                    "quantity": 10,
                    "price": 1298.40,
                    "timestamp": datetime(2026, 5, 10, 10, 15, tzinfo=timezone.utc).isoformat(),
                    "realized_pnl": None,
                    "is_loss": None,
                },
            ],
            "positions": [
                {
                    "symbol": "RELIANCE",
                    "side": "BUY",
                    "quantity": 10,
                    "avg_price": 1298.40,
                    "pnl": 120.0,
                }
            ],
            "holdings": [],
            "warnings": [],
        }

    monkeypatch.setattr(kite_client, "get_account_snapshot", fake_snapshot)

    ctx = await broker_client.get_kite_trading_context("session-1")

    assert [t.trade_id for t in ctx.recent_trades] == [
        "T-CLOSED",
        "OPEN-POS-RELIANCE-BUY",
    ]
    assert ctx.recent_trades[0].is_loss is True
    assert ctx.recent_trades[1].pnl is None


@pytest.mark.asyncio
async def test_live_kite_context_keeps_each_known_open_lot(monkeypatch):
    async def fake_snapshot(_session_id: str):
        return {
            "margins": {"available": 75_000, "used": 25_000, "total": 100_000},
            "summary": {
                "realized_pnl": 0.0,
                "realized_pnl_source": "unknown",
                "open_pnl": 80.0,
                "open_pnl_source": "exact",
                "open_positions_count": 1,
                "holdings_count": 0,
                "total_exposure": 20_000.0,
                "exposure_concentration": 1.0,
                "inferred_loss_streak": 0,
            },
            "trades": [
                {
                    "trade_id": "T-OPEN-1",
                    "symbol": "RELIANCE",
                    "action": "BUY",
                    "quantity": 5,
                    "quantity_remaining": 5,
                    "price": 1300.0,
                    "timestamp": datetime(2026, 5, 10, 9, 15, tzinfo=timezone.utc).isoformat(),
                    "realized_pnl": None,
                    "is_loss": None,
                },
                {
                    "trade_id": "T-OPEN-2",
                    "symbol": "RELIANCE",
                    "action": "BUY",
                    "quantity": 5,
                    "quantity_remaining": 5,
                    "price": 1310.0,
                    "timestamp": datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc).isoformat(),
                    "realized_pnl": None,
                    "is_loss": None,
                },
            ],
            "positions": [
                {
                    "symbol": "RELIANCE",
                    "side": "BUY",
                    "quantity": 10,
                    "avg_price": 1305.0,
                    "pnl": 80.0,
                }
            ],
            "holdings": [],
            "warnings": [],
        }

    monkeypatch.setattr(kite_client, "get_account_snapshot", fake_snapshot)

    ctx = await broker_client.get_kite_trading_context("session-1")

    assert [t.trade_id for t in ctx.recent_trades] == ["T-OPEN-1", "T-OPEN-2"]
    assert [t.quantity for t in ctx.recent_trades] == [5, 5]
    assert all(t.pnl is None for t in ctx.recent_trades)


@pytest.mark.asyncio
async def test_live_kite_holdings_are_visible_and_contribute_to_portfolio_risk(monkeypatch):
    async def fake_snapshot(_session_id: str):
        return {
            "margins": {"available": 80_000, "used": 20_000, "total": 100_000},
            "summary": {
                "realized_pnl": 0.0,
                "realized_pnl_source": "unknown",
                "open_pnl": 0.0,
                "open_pnl_source": "unknown",
                "open_positions_count": 0,
                "holdings_count": 1,
                "total_exposure": 80_000.0,
                "exposure_concentration": 1.0,
                "inferred_loss_streak": 0,
            },
            "trades": [],
            "positions": [],
            "holdings": [
                {
                    "symbol": "INFY",
                    "quantity": 50,
                    "avg_price": 1400.0,
                    "pnl": 10_000.0,
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr(kite_client, "get_account_snapshot", fake_snapshot)

    ctx = await broker_client.get_kite_trading_context("session-1")
    prompt = ai_engine.build_analysis_prompt(ctx)

    assert ctx.holdings_count == 1
    assert ctx.portfolio_positions == []
    assert ctx.portfolio_holdings == ["INFY qty=50 avg=1400.0 pnl=10000.0"]
    assert ctx.total_exposure == 80_000.0
    assert ctx.exposure_concentration == 1.0
    assert "holdings INFY qty=50 avg=1400.0 pnl=10000.0" in prompt
