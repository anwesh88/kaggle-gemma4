"""Repeatable warm-path benchmark harness for local Finsight latency work."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

sys.path.append(str(Path(__file__).resolve().parents[1]))

import ai_engine
import multimodal_engine
from models import Language, MarginData, Trade, TradingContext


@dataclass
class Series:
    p50_ms: float
    runs_ms: list[float]
    stage_p50_ms: dict[str, float]


def _ctx(kind: str) -> TradingContext:
    now = datetime.now(timezone.utc)
    trades: list[Trade] = []
    if kind in {"medium", "high"}:
        count = 2 if kind == "medium" else 4
        for i in range(count):
            trades.append(
                Trade(
                    trade_id=f"{kind}-{i}",
                    symbol="INFY",
                    action="BUY",
                    quantity=1,
                    price=100.0,
                    timestamp=now - timedelta(minutes=i + 1),
                    pnl=-100.0,
                    is_loss=True,
                )
            )
    margin_used = {"low": 10_000, "medium": 60_000, "high": 80_000}[kind]
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


def _chart_b64(offset: int = 0) -> str:
    image = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(image)
    draw.line((80, 620, 1200, 620), fill="black", width=3)
    draw.line((80, 80, 80, 620), fill="black", width=3)
    pts = [
        (100, 560 - offset),
        (220, 500 - offset),
        (340, 520 - offset),
        (460, 420 - offset),
        (580, 390 - offset),
        (700, 320 - offset),
        (820, 300 - offset),
        (940, 220 - offset),
        (1060, 180 - offset),
        (1180, 140 - offset),
    ]
    draw.line(pts, fill="#2563EB", width=6)
    out = io.BytesIO()
    image.save(out, format="PNG")
    normalized = multimodal_engine.preprocess_image_bytes(out.getvalue())
    return base64.b64encode(normalized).decode()


def _median_stage(stage_runs: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted({key for run in stage_runs for key in run})
    return {
        key: round(statistics.median([run.get(key, 0.0) for run in stage_runs]), 2)
        for key in keys
    }


async def _bench_behavior(kind: str, runs: int) -> Series:
    latencies: list[float] = []
    stages: list[dict[str, float]] = []
    ctx = _ctx(kind)
    for _ in range(runs):
        result = await ai_engine.analyze_behavior(ctx)
        total_ms = float(result.timings_ms.get("total_ms") or (result.inference_seconds or 0) * 1000)
        latencies.append(total_ms)
        stages.append(result.timings_ms)
    return Series(
        p50_ms=round(statistics.median(latencies), 2),
        runs_ms=latencies,
        stage_p50_ms=_median_stage(stages),
    )


async def _bench_chart(runs: int) -> Series:
    latencies: list[float] = []
    stages: list[dict[str, float]] = []
    context = {
        "recent_trades": [
            {"symbol": "INFY", "action": "BUY", "quantity": 1, "price": 100, "pnl": -100, "is_loss": True},
            {"symbol": "INFY", "action": "BUY", "quantity": 1, "price": 100, "pnl": -100, "is_loss": True},
        ],
        "loss_streak": 2,
        "margin_usage_pct": 60,
        "dna": {"total_sessions": 10, "high_risk_rate": 0.4, "avg_score": 420, "dominant_pattern": "Revenge Trading"},
    }
    # Use a slightly different screenshot every time. Reusing the exact same
    # image underestimates real latency because repeated visual inputs can
    # benefit from cache-like reuse inside the runtime.
    for idx in range(runs):
        result = await multimodal_engine.analyze_chart_full(
            _chart_b64(offset=idx * 3),
            symbol="INFY",
            context=context,
        )
        timings = result.get("_timings_ms") or {}
        latencies.append(float(timings.get("total_ms", 0.0)))
        stages.append(timings)
    return Series(
        p50_ms=round(statistics.median(latencies), 2),
        runs_ms=latencies,
        stage_p50_ms=_median_stage(stages),
    )


def _compare(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("behavior_low", "behavior_medium", "behavior_high", "chart"):
        before = float(baseline[key]["p50_ms"])
        after = float(current[key]["p50_ms"])
        out[key] = round((before - after) / before * 100, 2) if before else 0.0
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--assert-80", action="store_true")
    args = parser.parse_args()

    # Warm once before measuring the warm path.
    await ai_engine.warm_up_model()
    await multimodal_engine.warm_up_vision_model()

    report = {
        "behavior_low": asdict(await _bench_behavior("low", args.runs)),
        "behavior_medium": asdict(await _bench_behavior("medium", args.runs)),
        "behavior_high": asdict(await _bench_behavior("high", args.runs)),
        "chart": asdict(await _bench_chart(args.runs)),
    }

    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report["improvement_pct"] = _compare(report, baseline)
        if args.assert_80:
            failed = [k for k, v in report["improvement_pct"].items() if v < 80]
            if failed:
                raise SystemExit(f"<80% improvement for: {', '.join(failed)}")

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
