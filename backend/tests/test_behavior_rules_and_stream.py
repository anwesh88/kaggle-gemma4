import json
from datetime import datetime, timedelta, timezone

import pytest

import ai_engine
from behavior_rules import assess_behavior, detect_vow_violations
from models import Language, MarginData, Trade, TradingContext


def _ctx(*, losses: int = 0, margin_used: int = 0, wins: int = 0) -> TradingContext:
    now = datetime.now(timezone.utc)
    trades = []
    for idx in range(losses):
        trades.append(
            Trade(
                trade_id=f"L{idx}",
                symbol="INFY",
                action="BUY",
                quantity=1,
                price=100.0,
                timestamp=now - timedelta(minutes=idx + 1),
                pnl=-100.0,
                is_loss=True,
            )
        )
    for idx in range(wins):
        trades.append(
            Trade(
                trade_id=f"W{idx}",
                symbol="TCS",
                action="BUY",
                quantity=1,
                price=100.0,
                timestamp=now - timedelta(minutes=losses + idx + 1),
                pnl=100.0,
                is_loss=False,
            )
        )
    return TradingContext(
        recent_trades=trades,
        margin=MarginData(available=100_000 - margin_used, used=margin_used, total=100_000),
        trading_vows=[
            "I will stop trading after 2 consecutive losses",
            "I will not use more than 50% of my margin",
        ],
        preferred_language=Language.EN,
        source_mode="paper",
    )


def test_deterministic_scoring_and_vow_matching():
    ctx = _ctx(losses=4, margin_used=80_000)
    assessment = assess_behavior(ctx)

    assert detect_vow_violations(ctx) == [
        "I will stop trading after 2 consecutive losses",
        "I will not use more than 50% of my margin",
    ]
    assert assessment.score == 950
    assert assessment.risk_level == "high"
    assert assessment.crisis_score == 95
    assert assessment.inferred_pattern == "Addiction Loop"


def test_paper_portfolio_concentration_is_scored():
    ctx = _ctx()
    ctx.open_positions_count = 1
    ctx.total_exposure = 25_000
    ctx.exposure_concentration = 1.0

    assessment = assess_behavior(ctx)

    assert assessment.score == 100
    assert assessment.obvious_low_risk is False


@pytest.mark.asyncio
async def test_obvious_low_risk_skips_gemma(monkeypatch):
    async def should_not_run(*args, **kwargs):
        raise AssertionError("Gemma should have been skipped")

    monkeypatch.setattr(ai_engine, "_generate_behavior_json", should_not_run)
    result = await ai_engine.analyze_behavior(_ctx())

    assert result.analysis_source == "deterministic_fast_path"
    assert result.model_used is False
    assert result.behavioral_score == 0
    assert result.inference_seconds == 0.0


@pytest.mark.asyncio
async def test_high_risk_merges_deterministic_fields_with_gemma_language(monkeypatch):
    async def fake_generate(prompt: str, *, retry: bool = False):
        return ({
            "detected_pattern": "Revenge Trading",
            "nudge_message": "I am chasing losses through revenge trading, and I need to pause before deciding again.",
            "nudge_message_local": "",
        }, 0.25, json.dumps({"detected_pattern": "Revenge Trading"}))

    monkeypatch.setattr(ai_engine, "_generate_behavior_json", fake_generate)
    result = await ai_engine.analyze_behavior(_ctx(losses=4, margin_used=80_000))

    assert result.analysis_source == "gemma_backed"
    assert result.model_used is True
    assert result.behavioral_score == 950
    assert result.risk_level == "high"
    assert result.vows_violated == [
        "I will stop trading after 2 consecutive losses",
        "I will not use more than 50% of my margin",
    ]
    assert result.detected_pattern == "Revenge Trading"


@pytest.mark.asyncio
async def test_stream_emits_preview_before_result(monkeypatch):
    async def fake_analyze(ctx: TradingContext, assessment=None):
        return ai_engine._build_fast_path_analysis(
            ctx,
            assessment or assess_behavior(ctx),
            total_started_at=0.0,
            timings_ms={"deterministic_ms": 0.0},
        )

    monkeypatch.setattr(ai_engine, "analyze_behavior", fake_analyze)
    events = [event async for event in ai_engine.analyze_behavior_stream(_ctx())]
    types = [event["type"] for event in events]

    assert "preview" in types
    assert types.index("preview") < types.index("result")
