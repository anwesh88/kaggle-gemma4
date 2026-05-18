"""Deterministic behavioral scoring and fast-path heuristics.

Gemma is still responsible for language generation and nuanced pattern naming,
but the arithmetic rubric is exact enough to keep in Python. That removes
hundreds of generated tokens from the common path without changing the rules
the product claims to follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from models import TradingContext


@dataclass(frozen=True)
class DeterministicAssessment:
    score: int
    risk_level: str
    vows_violated: list[str]
    crisis_score: int
    crisis_detected: bool
    inferred_pattern: str
    obvious_low_risk: bool
    loss_count: int
    losses_last_hour: int
    consecutive_losses: int


def _closed_trades(ctx: TradingContext):
    return [t for t in ctx.recent_trades if t.pnl is not None]


def _losses_last_hour(ctx: TradingContext) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    return sum(
        1
        for t in _closed_trades(ctx)
        if t.is_loss and _as_utc(t.timestamp) >= cutoff
    )


def _consecutive_losses(ctx: TradingContext) -> int:
    streak = 0
    for trade in reversed(_closed_trades(ctx)):
        if trade.is_loss:
            streak += 1
        else:
            break
    return streak


def _as_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _extract_threshold(vow: str, default: int) -> int:
    match = re.search(r"(\d+)", vow)
    return int(match.group(1)) if match else default


def detect_vow_violations(ctx: TradingContext) -> list[str]:
    violations: list[str] = []
    losses_last_hour = _losses_last_hour(ctx)
    consecutive_losses = _consecutive_losses(ctx)
    margin_pct = ctx.margin.usage_ratio * 100

    for vow in ctx.trading_vows:
        text = vow.lower()
        violated = False

        if "consecutive loss" in text:
            violated = consecutive_losses >= _extract_threshold(text, 2)
        elif "margin" in text:
            violated = margin_pct > _extract_threshold(text, 50)
        elif "revenge" in text:
            violated = losses_last_hour >= 2 or consecutive_losses >= 2 or ctx.inferred_loss_streak >= 2

        if violated:
            violations.append(vow)

    return violations


def assess_behavior(ctx: TradingContext) -> DeterministicAssessment:
    closed = _closed_trades(ctx)
    loss_count = sum(1 for trade in closed if trade.is_loss)
    losses_last_hour = _losses_last_hour(ctx)
    consecutive_losses = _consecutive_losses(ctx)
    margin_ratio = ctx.margin.usage_ratio
    vows_violated = detect_vow_violations(ctx)

    score = 0
    if losses_last_hour >= 2:
        score += 200
    if loss_count >= 4:
        score += 200
    if margin_ratio > 0.70:
        score += 150
    score += 200 * len(vows_violated)
    if ctx.historical_loss_rate > 0.50:
        score += 150
    if closed and not closed[-1].is_loss:
        score -= 100

    if ctx.source_mode == "kite":
        if (ctx.day_realized_pnl or 0) < 0:
            score += 100
        if (ctx.open_pnl or 0) < 0:
            score += 75
        if ctx.inferred_loss_streak >= 2:
            score += 150

    if ctx.exposure_concentration > 0.50:
        score += 100

    score = max(0, min(1000, score))
    risk_level = "high" if score >= 600 else "medium" if score >= 300 else "low"
    crisis_score = max(0, min(100, round(score / 10)))

    if loss_count >= 4:
        inferred_pattern = "Addiction Loop"
    elif margin_ratio > 0.70:
        inferred_pattern = "Over-Leveraging"
    elif losses_last_hour >= 2 or consecutive_losses >= 2 or ctx.inferred_loss_streak >= 2:
        inferred_pattern = "Revenge Trading"
    else:
        inferred_pattern = "Healthy Trading"

    account_risk = any(
        [
            (ctx.day_realized_pnl or 0) < 0,
            (ctx.open_pnl or 0) < 0,
            ctx.inferred_loss_streak >= 2,
            ctx.exposure_concentration > 0.50,
        ]
    )
    obvious_low_risk = (
        score <= 150
        and loss_count == 0
        and losses_last_hour == 0
        and margin_ratio <= 0.50
        and not vows_violated
        and ctx.historical_loss_rate <= 0.50
        and not account_risk
    )

    return DeterministicAssessment(
        score=score,
        risk_level=risk_level,
        vows_violated=vows_violated,
        crisis_score=crisis_score,
        crisis_detected=crisis_score > 70,
        inferred_pattern=inferred_pattern,
        obvious_low_risk=obvious_low_risk,
        loss_count=loss_count,
        losses_last_hour=losses_last_hour,
        consecutive_losses=consecutive_losses,
    )
