import json
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

import ai_engine
from models import Language, MarginData, Trade, TradingContext


@pytest.mark.asyncio
async def test_analyze_behavior_sends_compact_context_to_gemma(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_generate(prompt: str, *, retry: bool = False):
        captured["prompt"] = prompt
        return ({
            "detected_pattern": "Over-Leveraging",
            "nudge_message": "",
            "nudge_message_local": "",
        }, 0.12, json.dumps({"detected_pattern": "Over-Leveraging"}))

    monkeypatch.setattr(ai_engine, "_generate_behavior_json", fake_generate)

    ctx = TradingContext(
        recent_trades=[
            Trade(
                trade_id="PAPER-1",
                symbol="RELIANCE",
                action="BUY",
                quantity=10,
                price=1298.40,
                timestamp=datetime.now(timezone.utc),
                pnl=None,
                is_loss=False,
            )
        ],
        margin=MarginData(available=40_000, used=60_000, total=100_000),
        trading_vows=[
            "I will stop trading after 2 consecutive losses",
            "I will not use more than 50% of my margin",
        ],
        preferred_language=Language.EN,
        source_mode="paper",
        open_positions_count=1,
        total_exposure=12_984.0,
        exposure_concentration=1.0,
        portfolio_positions=["BUY RELIANCE qty=10 avg=1298.4"],
    )

    result = await ai_engine.analyze_behavior(ctx)

    assert "Exact rubric already computed in Python" in captured["prompt"]
    assert "Session: 1 trades (0 closed, 1 open)" in captured["prompt"]
    assert "BUY RELIANCE qty=10 @ Rs.1298.40 pnl=unrealized OPEN" in captured["prompt"]
    assert "Portfolio: positions BUY RELIANCE qty=10 avg=1298.4" in captured["prompt"]
    assert "I will not use more than 50% of my margin" in captured["prompt"]
    assert result.behavioral_score == 300
    assert result.detected_pattern == "Over-Leveraging"
    assert result.vows_violated == ["I will not use more than 50% of my margin"]
    assert result.analysis_source == "gemma_backed"
    assert "Python checked 1 trade(s) (1 open, 0 closed)" in (result.thinking_log or "")
    assert "No trades placed yet" not in (result.thinking_log or "")


@pytest.mark.asyncio
async def test_analyze_behavior_timeout_is_explicit_unavailable(monkeypatch):
    async def fake_generate(prompt: str, *, retry: bool = False):
        raise asyncio.TimeoutError("simulated model stall")

    import asyncio
    monkeypatch.setattr(ai_engine, "_generate_behavior_json", fake_generate)

    now = datetime.now(timezone.utc)
    ctx = TradingContext(
        recent_trades=[
            Trade(
                trade_id="L1",
                symbol="INFY",
                action="BUY",
                quantity=1,
                price=100.0,
                timestamp=now - timedelta(minutes=10),
                pnl=-100.0,
                is_loss=True,
            ),
            Trade(
                trade_id="L2",
                symbol="INFY",
                action="BUY",
                quantity=1,
                price=100.0,
                timestamp=now - timedelta(minutes=5),
                pnl=-100.0,
                is_loss=True,
            ),
        ],
        margin=MarginData(available=20_000, used=80_000, total=100_000),
        trading_vows=["I will stop trading after 2 consecutive losses"],
        preferred_language=Language.EN,
        source_mode="paper",
    )

    result = await ai_engine.analyze_behavior(ctx)

    assert result.detected_pattern == "Gemma unavailable"
    assert result.inference_seconds is None
    assert result.analysis_source == "unavailable"
    assert "no model insight produced" in (result.thinking_log or "")
