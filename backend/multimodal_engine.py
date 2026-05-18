"""
multimodal_engine.py - Vision analysis of trading chart screenshots.

Gemma stays central to visual perception and natural-language insight, while
Python handles the deterministic score assembly that should not consume model
tokens on a CPU-bound laptop.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import time
from typing import Any

import numpy as np
from PIL import Image, ImageOps

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", os.getenv("OLLAMA_MODEL", "gemma4:e2b"))
OLLAMA_TIMEOUT_S = int(os.getenv("OLLAMA_VISION_TIMEOUT_S", "300"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
# 512px is enough for coarse chart structure while avoiding the enormous
# visual-token cost jump we measured above that size on CPU.
VISION_MAX_EDGE = int(os.getenv("OLLAMA_VISION_MAX_EDGE", "512"))
CHART_LANGUAGE_MODE = os.getenv("OLLAMA_CHART_LANGUAGE_MODE", "deterministic").lower()
CHART_FAST_PATH_ENABLED = os.getenv("OLLAMA_CHART_FAST_PATH", "true").lower() not in {"0", "false", "no"}
CHART_FAST_PATH_MIN_CONFIDENCE = float(os.getenv("OLLAMA_CHART_FAST_PATH_MIN_CONFIDENCE", "0.58"))


def _i(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _parse_json_forgiving(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    candidate = match.group() if match else raw
    repaired = _repair_json(candidate)
    if repaired is None:
        return None
    try:
        return json.loads(repaired)
    except Exception as e:
        print(f"[Multimodal] json_parse after repair: {e}")
        return None


def _repair_json(s: str) -> str | None:
    if not s:
        return None
    out = s.strip()
    out = re.sub(r"^```(?:json)?\s*", "", out)
    out = re.sub(r"\s*```\s*$", "", out)
    out = re.sub(r",\s*([}\]])", r"\1", out)
    out = re.sub(r'(["\]}0-9])\s*\n\s*(")', r"\1,\n\2", out)
    out = re.sub(r'(["\]}0-9])\s+(?=")', r"\1,", out)
    open_curly = out.count("{") - out.count("}")
    open_square = out.count("[") - out.count("]")
    if open_square > 0:
        out += "]" * open_square
    if open_curly > 0:
        out += "}" * open_curly
    return out


def _strip_data_url(b64: str) -> str:
    if b64.startswith("data:") and "," in b64:
        return b64.split(",", 1)[1]
    return b64


def preprocess_image_bytes(contents: bytes, max_edge: int = VISION_MAX_EDGE) -> bytes:
    """Normalize orientation, remove metadata, and bound the longest edge."""
    with Image.open(io.BytesIO(contents)) as image:
        image = ImageOps.exif_transpose(image)
        if max(image.size) > max_edge:
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()


def _rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) <= 2:
        return values.astype(float)
    radius = max(1, window // 2)
    padded = np.pad(values.astype(float), (radius, radius), mode="edge")
    return np.array([
        float(np.median(padded[i:i + (radius * 2) + 1]))
        for i in range(len(values))
    ])


def _heuristic_chart_vision_from_bytes(contents: bytes) -> tuple[dict[str, str] | None, float, dict[str, float]]:
    """
    Fast path for ordinary chart screenshots.

    Gemma vision is still the fallback for ambiguous images, but spending
    40-50 seconds of CPU on obvious rising/falling charts is wasteful. Most
    broker/charting screenshots use saturated plot colors against a plain
    background; we reduce those pixels to a rough price path and classify the
    path deterministically in a few milliseconds.
    """
    started_at = time.perf_counter()
    try:
        with Image.open(io.BytesIO(contents)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            arr = np.asarray(image, dtype=np.int16)
    except Exception:
        return None, 0.0, {"reason": 1.0}

    height, width = arr.shape[:2]
    if height < 48 or width < 64:
        return None, 0.0, {"reason": 1.0}

    # Ignore common axis/title/toolbar gutters. The central plotting area is
    # where the signal lives; text labels otherwise pollute the mask.
    top = max(0, round(height * 0.06))
    bottom = min(height, round(height * 0.88))
    left = max(0, round(width * 0.05))
    right = min(width, round(width * 0.96))
    plot = arr[top:bottom, left:right]
    ph, pw = plot.shape[:2]

    corner_patches = np.concatenate([
        plot[: max(4, ph // 12), : max(4, pw // 12)].reshape(-1, 3),
        plot[: max(4, ph // 12), -max(4, pw // 12):].reshape(-1, 3),
        plot[-max(4, ph // 12):, : max(4, pw // 12)].reshape(-1, 3),
        plot[-max(4, ph // 12):, -max(4, pw // 12):].reshape(-1, 3),
    ])
    background = np.median(corner_patches, axis=0)
    distance = np.linalg.norm(plot - background, axis=2)
    saturation = plot.max(axis=2) - plot.min(axis=2)

    # Prefer colored candles/price lines. If the screenshot is monochrome,
    # fall back to strong contrast from the background.
    colored_mask = (saturation >= 42) & (distance >= 34)
    mask = colored_mask
    colored_ratio = float(colored_mask.mean())
    if colored_ratio < 0.0015:
        mask = distance >= 68

    mask_ratio = float(mask.mean())
    if mask_ratio < 0.001:
        return None, 0.0, {"mask_ratio": round(mask_ratio, 4)}

    xs: list[int] = []
    ys: list[float] = []
    for x in range(pw):
        rows = np.flatnonzero(mask[:, x])
        if rows.size == 0:
            continue
        # Very dense columns are usually panel borders / y-axes, not price.
        if rows.size > ph * 0.55:
            continue
        xs.append(x)
        ys.append(float(np.median(rows)))

    if len(xs) < max(28, round(pw * 0.10)):
        return None, 0.0, {
            "mask_ratio": round(mask_ratio, 4),
            "coverage": round(len(xs) / max(pw, 1), 4),
        }

    x_arr = np.asarray(xs, dtype=float)
    y_arr = np.asarray(ys, dtype=float)
    smoothed = _rolling_median(y_arr, max(3, min(11, len(y_arr) // 18 * 2 + 1)))
    span = max(3, len(smoothed) // 7)
    first = float(np.median(smoothed[:span]))
    last = float(np.median(smoothed[-span:]))
    trend_delta = first - last  # positive => price rises left-to-right
    normalized_delta = trend_delta / max(ph, 1)

    trend_threshold = 0.075
    if normalized_delta > trend_threshold:
        trend = "up"
    elif normalized_delta < -trend_threshold:
        trend = "down"
    else:
        trend = "sideways"

    overall_slope = normalized_delta
    tail_span = max(6, len(smoothed) // 3)
    tail_delta = float(np.median(smoothed[-tail_span:-max(1, tail_span // 3)]) - np.median(smoothed[-max(1, tail_span // 3):]))
    tail_norm = tail_delta / max(ph, 1)
    same_direction = np.sign(tail_norm) == np.sign(overall_slope) or abs(overall_slope) < 1e-6

    if trend == "sideways":
        momentum = "weakening"
    elif not same_direction and abs(tail_norm) >= 0.03:
        momentum = "exhausted"
    elif abs(tail_norm) < max(0.025, abs(overall_slope) * 0.38):
        momentum = "weakening"
    else:
        momentum = "strong"

    fitted = np.interp(x_arr, [x_arr.min(), x_arr.max()], [first, last])
    residual = smoothed - fitted
    roughness = float(np.std(residual) / max(ph, 1))
    step_noise = float(np.mean(np.abs(np.diff(smoothed))) / max(ph, 1)) if len(smoothed) > 1 else 0.0
    volatility_score = max(roughness, step_noise * 2.8)
    if volatility_score < 0.018:
        volatility = "low"
    elif volatility_score < 0.050:
        volatility = "normal"
    elif volatility_score < 0.105:
        volatility = "elevated"
    else:
        volatility = "extreme"

    coverage = len(xs) / max(pw, 1)
    direction_strength = min(1.0, abs(normalized_delta) / 0.18)
    color_bonus = 0.15 if colored_ratio >= 0.0015 else 0.0
    confidence = min(
        0.98,
        0.22
        + min(coverage, 0.55) * 0.75
        + direction_strength * 0.35
        + color_bonus,
    )
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    meta = {
        "mask_ratio": round(mask_ratio, 4),
        "coverage": round(coverage, 4),
        "normalized_delta": round(normalized_delta, 4),
        "volatility_score": round(volatility_score, 4),
        "elapsed_ms": elapsed_ms,
    }
    return {
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
    }, round(confidence, 4), meta


def _image_bytes_from_b64(image_b64: str) -> bytes | None:
    try:
        return base64.b64decode(_strip_data_url(image_b64), validate=True)
    except Exception:
        return None


def _summarize_trader_context(ctx: dict[str, Any] | None) -> str:
    if not ctx:
        return "No prior trading history available."

    bits: list[str] = []
    dna = ctx.get("dna") or {}
    if dna:
        sessions = dna.get("total_sessions") or dna.get("sessions") or 0
        loss_rate = dna.get("loss_rate") or dna.get("high_risk_rate") or 0
        avg_score = dna.get("average_score") or dna.get("avg_score") or 0
        dom = dna.get("dominant_pattern") or "none"
        bits.append(
            f"Trader DNA: {sessions} sessions, {loss_rate:.0%} loss/high-risk rate, "
            f"avg score {avg_score}, dominant pattern '{dom}'."
        )

    recent = ctx.get("recent_trades") or []
    if recent:
        losses = sum(1 for t in recent if t.get("is_loss"))
        wins = sum(1 for t in recent if t.get("pnl") is not None and not t.get("is_loss"))
        symbols = ", ".join({t.get("symbol", "?") for t in recent[:6]}) or "-"
        bits.append(f"Today: {len(recent)} trades, {losses} losses, {wins} wins; symbols {symbols}.")

    margin_pct = ctx.get("margin_usage_pct")
    if isinstance(margin_pct, (int, float)):
        bits.append(f"Margin currently {round(margin_pct)}%.")

    streak = ctx.get("loss_streak")
    if isinstance(streak, int) and streak > 0:
        bits.append(f"Active loss streak {streak}.")

    return " ".join(bits) if bits else "No prior trading history available."


def _stub(behavioral_warning: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "market_state": "unknown",
        "market_structure": {
            "trend": "unknown",
            "momentum": "unknown",
            "volatility": "unknown",
            "volume_confirmation": "unknown",
            "key_observation": "Chart could not be analyzed.",
        },
        "behavioral_risk": {
            "fomo_probability": 0,
            "revenge_probability": 0,
            "panic_probability": 0,
            "overconfidence_risk": 0,
            "emotional_risk_level": "unknown",
            "primary_concern": "-",
        },
        "decision_quality": {
            "score": 0,
            "rating": "unknown",
            "entry_timing": "-",
            "risk_reward": "-",
            "stop_placement": "-",
            "position_sizing": "-",
        },
        "personalized_insight": behavioral_warning,
        "behavioral_warning": behavioral_warning,
    }
    base.update(extra)
    return base


def _vision_prompt(symbol: str) -> str:
    symbol_hint = f" for {symbol}" if symbol else ""
    return f'''Read the uploaded chart{symbol_hint}.
Reply ONLY with JSON:
{{
  "trend": "up or down or sideways",
  "momentum": "strong or weakening or exhausted",
  "volatility": "low or normal or elevated or extreme"
}}'''


def _language_prompt(
    structure: dict[str, Any],
    market_state: str,
    risk: dict[str, Any],
    context: dict[str, Any] | None,
) -> str:
    trader_ctx = _summarize_trader_context(context)
    return f'''You are Finsight OS, a behavioral trading guardian.
Trader context: {trader_ctx}
Chart summary: market {market_state}; trend {structure["trend"]}; momentum {structure["momentum"]}; volatility {structure["volatility"]}.
Behavioral risk: primary concern {risk["primary_concern"]}; level {risk["emotional_risk_level"]}.

Reply ONLY with JSON:
{{
  "personalized_insight": "one short sentence linking this setup to the trader context",
  "behavioral_warning": "one short action sentence"
}}'''


def _is_complete_vision_data(data: dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    return all(isinstance(data.get(k), str) for k in ("trend", "momentum", "volatility"))


def _is_complete_language_data(data: dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("personalized_insight"), str) and isinstance(data.get("behavioral_warning"), str)


def _vision_options(*, retry: bool) -> dict[str, Any]:
    return {
        "temperature": 0.1,
        "num_predict": _i("OLLAMA_VISION_FALLBACK_NUM_PREDICT", 96) if retry else _i("OLLAMA_VISION_NUM_PREDICT", 64),
        "num_ctx": _i("OLLAMA_VISION_FALLBACK_NUM_CTX", 1280) if retry else _i("OLLAMA_VISION_NUM_CTX", 1024),
        "num_thread": _i("OLLAMA_NUM_THREAD", 8),
        "num_gpu": _i("OLLAMA_NUM_GPU", 0),
    }


def _language_options(*, retry: bool) -> dict[str, Any]:
    return {
        "temperature": 0.2,
        "num_predict": _i("OLLAMA_LANGUAGE_FALLBACK_NUM_PREDICT", 128) if retry else _i("OLLAMA_LANGUAGE_NUM_PREDICT", 96),
        "num_ctx": _i("OLLAMA_LANGUAGE_FALLBACK_NUM_CTX", 1024) if retry else _i("OLLAMA_LANGUAGE_NUM_CTX", 768),
        "num_thread": _i("OLLAMA_NUM_THREAD", 8),
        "num_gpu": _i("OLLAMA_NUM_GPU", 0),
    }


async def _generate_chart_vision_json(prompt: str, image_b64: str, *, retry: bool = False) -> tuple[dict[str, Any] | None, float, str]:
    import ollama

    start = time.perf_counter()
    response = await asyncio.wait_for(
        ollama.AsyncClient(host=OLLAMA_HOST).generate(
            model=OLLAMA_VISION_MODEL,
            prompt=prompt,
            images=[image_b64],
            format="json",
            options=_vision_options(retry=retry),
            keep_alive=OLLAMA_KEEP_ALIVE,
        ),
        timeout=OLLAMA_TIMEOUT_S,
    )
    elapsed = time.perf_counter() - start
    raw = (response.get("response") or "").strip()
    return _parse_json_forgiving(raw), elapsed, raw


async def _generate_chart_language_json(prompt: str, *, retry: bool = False) -> tuple[dict[str, Any] | None, float, str]:
    import ollama

    start = time.perf_counter()
    response = await asyncio.wait_for(
        ollama.AsyncClient(host=OLLAMA_HOST).generate(
            model=OLLAMA_VISION_MODEL,
            prompt=prompt,
            format="json",
            options=_language_options(retry=retry),
            keep_alive=OLLAMA_KEEP_ALIVE,
        ),
        timeout=OLLAMA_TIMEOUT_S,
    )
    elapsed = time.perf_counter() - start
    raw = (response.get("response") or "").strip()
    return _parse_json_forgiving(raw), elapsed, raw


def _clamp(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _assemble_behavioral_risk(
    structure: dict[str, Any],
    market_state: str,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    ctx = context or {}
    recent = ctx.get("recent_trades") or []
    dna = ctx.get("dna") or {}
    loss_streak = int(ctx.get("loss_streak") or 0)
    recent_losses = sum(1 for t in recent if t.get("is_loss"))
    recent_wins = sum(1 for t in recent if t.get("pnl") is not None and not t.get("is_loss"))
    dominant = str(dna.get("dominant_pattern") or "").lower()

    trend = str(structure.get("trend") or "unknown").lower()
    momentum = str(structure.get("momentum") or "unknown").lower()
    volatility = str(structure.get("volatility") or "unknown").lower()
    state = market_state.lower()

    fomo = 0
    if trend == "up" and momentum == "strong":
        fomo += 45
    if state == "trending":
        fomo += 15
    if dominant == "fomo":
        fomo += 15

    revenge = min(80, loss_streak * 25 + recent_losses * 8)
    if dominant == "revenge trading":
        revenge += 10

    panic = 0
    if trend == "down":
        panic += 35
    if volatility in {"elevated", "extreme"}:
        panic += 25
    if dominant == "panic selling":
        panic += 15

    overconfidence = recent_wins * 15
    if trend == "up" and momentum == "strong":
        overconfidence += 15
    if dominant == "overconfidence":
        overconfidence += 15

    scores = {
        "fomo_probability": _clamp(fomo),
        "revenge_probability": _clamp(revenge),
        "panic_probability": _clamp(panic),
        "overconfidence_risk": _clamp(overconfidence),
    }
    max_key = max(scores, key=scores.get)
    max_score = scores[max_key]
    label_map = {
        "fomo_probability": "late-entry FOMO",
        "revenge_probability": "revenge trading after losses",
        "panic_probability": "panic selling",
        "overconfidence_risk": "oversizing after wins",
    }
    if max_score >= 70:
        emotional_level = "high"
    elif max_score >= 40:
        emotional_level = "medium"
    else:
        emotional_level = "low"
    return {
        **scores,
        "emotional_risk_level": emotional_level,
        "primary_concern": label_map[max_key] if max_score else "-",
    }


def _assemble_decision_quality(
    structure: dict[str, Any],
    market_state: str,
    risk: dict[str, Any],
) -> dict[str, Any]:
    trend = str(structure.get("trend") or "unknown").lower()
    momentum = str(structure.get("momentum") or "unknown").lower()
    volatility = str(structure.get("volatility") or "unknown").lower()
    state = market_state.lower()

    score = 78
    if state == "ranging" or trend == "sideways":
        score -= 10
    if momentum == "weakening":
        score -= 10
    elif momentum == "exhausted":
        score -= 18
    if volatility == "elevated":
        score -= 12
    elif volatility == "extreme":
        score -= 22
    score -= round(max(
        risk.get("fomo_probability", 0),
        risk.get("revenge_probability", 0),
        risk.get("panic_probability", 0),
        risk.get("overconfidence_risk", 0),
    ) * 0.2)
    score = _clamp(score)

    rating = "good" if score >= 70 else "average" if score >= 45 else "poor"
    if momentum == "exhausted":
        entry_timing = "late"
    elif trend in {"up", "down"} and momentum == "strong":
        entry_timing = "on-time"
    else:
        entry_timing = "early"
    risk_reward = "favorable" if score >= 75 else "acceptable" if score >= 50 else "poor"
    stop_placement = (
        "Use a wider technical stop or reduce size in high volatility."
        if volatility in {"elevated", "extreme"}
        else "Place the stop beyond the invalidation level, not inside chart noise."
    )
    position_sizing = "reduce" if risk.get("emotional_risk_level") == "high" else "small" if volatility in {"elevated", "extreme"} else "standard"
    return {
        "score": score,
        "rating": rating,
        "entry_timing": entry_timing,
        "risk_reward": risk_reward,
        "stop_placement": stop_placement,
        "position_sizing": position_sizing,
    }


def _merge_chart_payload(
    vision_data: dict[str, Any],
    language_data: dict[str, Any],
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    warning = language_data.get("behavioral_warning") or language_data.get("personalized_insight") or "Review this chart carefully before placing any trade."
    merged = _stub(str(warning))
    trend = str(vision_data.get("trend") or "unknown").lower()
    momentum = str(vision_data.get("momentum") or "unknown").lower()
    volatility = str(vision_data.get("volatility") or "unknown").lower()
    market_state = "volatile" if volatility == "extreme" else "ranging" if trend == "sideways" else "trending"
    merged["market_state"] = market_state
    merged["market_structure"].update({
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume_confirmation": "unclear",
        "key_observation": _observation_sentence(trend, momentum, volatility),
    })
    if isinstance(language_data.get("personalized_insight"), str):
        merged["personalized_insight"] = language_data["personalized_insight"]
    if isinstance(language_data.get("behavioral_warning"), str):
        merged["behavioral_warning"] = language_data["behavioral_warning"]
    merged["behavioral_risk"] = _assemble_behavioral_risk(
        merged["market_structure"], merged["market_state"], context
    )
    merged["decision_quality"] = _assemble_decision_quality(
        merged["market_structure"], merged["market_state"], merged["behavioral_risk"]
    )
    return merged


def _observation_sentence(trend: str, momentum: str, volatility: str) -> str:
    if trend == "sideways":
        return f"Price is moving sideways with {volatility} volatility."
    if trend in {"up", "down"}:
        return f"Price is trending {trend} with {momentum} momentum and {volatility} volatility."
    return "The chart structure is unclear from the uploaded image."


def _deterministic_chart_language(
    structure: dict[str, Any],
    market_state: str,
    risk: dict[str, Any],
    context: dict[str, Any] | None,
) -> dict[str, str]:
    ctx = context or {}
    dna = ctx.get("dna") or {}
    dominant = str(dna.get("dominant_pattern") or "").strip()
    loss_streak = int(ctx.get("loss_streak") or 0)
    trend = str(structure.get("trend") or "unclear")
    momentum = str(structure.get("momentum") or "unclear")
    volatility = str(structure.get("volatility") or "unclear")

    if loss_streak >= 2 and dominant:
        insight = (
            f"This {trend} setup arrives during a {loss_streak}-trade loss streak "
            f"and echoes your {dominant.lower()} history."
        )
    elif dominant:
        insight = f"This {trend} setup intersects with your recorded {dominant.lower()} pattern."
    else:
        insight = f"This chart is {trend} with {momentum} momentum and {volatility} volatility."

    concern = str(risk.get("primary_concern") or "-")
    if concern != "-":
        warning = f"Your main risk here is {concern}; wait for confirmation before acting."
    elif market_state == "ranging":
        warning = "Do not force a trade while the chart is ranging; wait for confirmation."
    else:
        warning = "Keep size disciplined and trade only if the setup still matches your plan."
    return {
        "personalized_insight": insight,
        "behavioral_warning": warning,
    }


async def analyze_chart_image(image_b64: str, symbol: str = "", context: dict[str, Any] | None = None) -> str:
    res = await analyze_chart_full(image_b64, symbol=symbol, context=context)
    return res.get("personalized_insight") or res.get("behavioral_warning") or "Unable to analyze chart. Please review carefully before trading."


async def warm_up_vision_model() -> None:
    """Prime the visual path once so warm chart requests avoid first-use cost."""
    try:
        synthetic = Image.new("RGB", (512, 288), "white")
        from PIL import ImageDraw
        draw = ImageDraw.Draw(synthetic)
        draw.line((24, 250, 488, 250), fill="black", width=2)
        draw.line((24, 24, 24, 250), fill="black", width=2)
        draw.line(
            [(32, 230), (96, 210), (160, 216), (224, 170), (288, 152), (352, 122), (416, 92), (480, 64)],
            fill="#2563EB",
            width=4,
        )
        buf = io.BytesIO()
        synthetic.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode()
        print(f"[Multimodal] Pre-warming vision path on {OLLAMA_VISION_MODEL}...", flush=True)
        _, elapsed, _ = await _generate_chart_vision_json(_vision_prompt(""), image_b64)
        print(f"[Multimodal] Vision pre-warm complete in {elapsed:.1f}s", flush=True)
    except Exception as e:
        print(f"[Multimodal] Vision pre-warm skipped ({type(e).__name__}: {e})", flush=True)


async def analyze_chart_full(image_b64: str, symbol: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    total_started_at = time.perf_counter()
    image_b64 = _strip_data_url(image_b64)
    prompt_started_at = time.perf_counter()
    vision_prompt = _vision_prompt(symbol)
    timings_ms: dict[str, float] = {
        "prompt_build_ms": round((time.perf_counter() - prompt_started_at) * 1000, 2)
    }
    image_bytes = _image_bytes_from_b64(image_b64)

    if CHART_FAST_PATH_ENABLED and image_bytes is not None:
        fast_started_at = time.perf_counter()
        fast_vision, fast_confidence, fast_meta = _heuristic_chart_vision_from_bytes(image_bytes)
        timings_ms["fast_path_ms"] = round((time.perf_counter() - fast_started_at) * 1000, 2)
        if fast_vision and fast_confidence >= CHART_FAST_PATH_MIN_CONFIDENCE:
            structure_started_at = time.perf_counter()
            trend = str(fast_vision.get("trend") or "unknown").lower()
            momentum = str(fast_vision.get("momentum") or "unknown").lower()
            volatility = str(fast_vision.get("volatility") or "unknown").lower()
            provisional_structure = {
                "trend": trend,
                "momentum": momentum,
                "volatility": volatility,
                "volume_confirmation": "unclear",
                "key_observation": _observation_sentence(trend, momentum, volatility),
            }
            market_state = "volatile" if volatility == "extreme" else "ranging" if trend == "sideways" else "trending"
            risk = _assemble_behavioral_risk(provisional_structure, market_state, context)
            language_data = _deterministic_chart_language(provisional_structure, market_state, risk, context)
            timings_ms["deterministic_structure_ms"] = round((time.perf_counter() - structure_started_at) * 1000, 2)
            timings_ms["language_model_ms"] = 0.0
            assembly_started_at = time.perf_counter()
            merged = _merge_chart_payload(fast_vision, language_data, context)
            timings_ms["parse_assembly_ms"] = round((time.perf_counter() - assembly_started_at) * 1000, 2)
            timings_ms["vision_model_ms"] = 0.0
            timings_ms["model_ms"] = 0.0
            timings_ms["total_ms"] = round((time.perf_counter() - total_started_at) * 1000, 2)
            merged["_timings_ms"] = timings_ms
            merged["_analysis_source"] = "deterministic_chart_fast_path"
            merged["_fast_path"] = {
                "confidence": fast_confidence,
                **fast_meta,
            }
            print(
                f"[Multimodal] chart fast path confidence={fast_confidence:.2f}; "
                f"total={timings_ms['total_ms']:.2f}ms"
            )
            return merged
        timings_ms["fast_path_confidence"] = fast_confidence

    import ollama

    try:
        vision_data, vision_elapsed, raw = await _generate_chart_vision_json(vision_prompt, image_b64)
        timings_ms["vision_model_ms"] = round(vision_elapsed * 1000, 2)
        if not _is_complete_vision_data(vision_data):
            print("[Multimodal] incomplete compact vision output; retrying once with fallback budget")
            vision_data, retry_elapsed, raw = await _generate_chart_vision_json(vision_prompt, image_b64, retry=True)
            timings_ms["vision_retry_model_ms"] = round(retry_elapsed * 1000, 2)
            timings_ms["vision_model_ms"] += timings_ms["vision_retry_model_ms"]
    except asyncio.TimeoutError:
        return _stub(
            f"Chart analysis exceeded {OLLAMA_TIMEOUT_S}s while using `{OLLAMA_VISION_MODEL}`.",
            error=f"Vision inference exceeded {OLLAMA_TIMEOUT_S}s",
        )
    except ollama.ResponseError as e:  # type: ignore[attr-defined]
        msg = str(e)
        if "not found" in msg.lower() or "no such model" in msg.lower():
            return _stub(
                f"Vision model `{OLLAMA_VISION_MODEL}` is not available locally.",
                error="model_not_pulled",
            )
        print(f"[Multimodal] Ollama error: {e}")
        return _stub("Chart not analyzed - vision model error.", error=str(e))
    except Exception as e:
        print(f"[Multimodal] Vision analysis failed: {type(e).__name__}: {e}")
        return _stub(
            "Unable to analyze chart. Please review carefully before trading.",
            error=f"{type(e).__name__}: {e}",
        )

    if not _is_complete_vision_data(vision_data):
        return _stub(
            "Chart shows market activity - review carefully before trading.",
            error="vision_json_parse_failed",
            raw=raw[:300],
        )

    structure_started_at = time.perf_counter()
    trend = str(vision_data.get("trend") or "unknown").lower()
    momentum = str(vision_data.get("momentum") or "unknown").lower()
    volatility = str(vision_data.get("volatility") or "unknown").lower()
    provisional_structure = {
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume_confirmation": "unclear",
        "key_observation": _observation_sentence(trend, momentum, volatility),
    }
    market_state = "volatile" if volatility == "extreme" else "ranging" if trend == "sideways" else "trending"
    risk = _assemble_behavioral_risk(provisional_structure, market_state, context)
    language_prompt = _language_prompt(provisional_structure, market_state, risk, context)
    timings_ms["deterministic_structure_ms"] = round((time.perf_counter() - structure_started_at) * 1000, 2)

    language_raw = ""
    if CHART_LANGUAGE_MODE == "gemma":
        try:
            language_data, language_elapsed, language_raw = await _generate_chart_language_json(language_prompt)
            timings_ms["language_model_ms"] = round(language_elapsed * 1000, 2)
            if not _is_complete_language_data(language_data):
                print("[Multimodal] incomplete language output; retrying once with fallback budget")
                language_data, retry_elapsed, language_raw = await _generate_chart_language_json(language_prompt, retry=True)
                timings_ms["language_retry_model_ms"] = round(retry_elapsed * 1000, 2)
                timings_ms["language_model_ms"] += timings_ms["language_retry_model_ms"]
        except asyncio.TimeoutError:
            return _stub(
                f"Chart explanation exceeded {OLLAMA_TIMEOUT_S}s while using `{OLLAMA_VISION_MODEL}`.",
                error=f"Language inference exceeded {OLLAMA_TIMEOUT_S}s",
            )
        except Exception as e:
            print(f"[Multimodal] Language generation failed: {type(e).__name__}: {e}")
            return _stub(
                "Unable to explain chart. Please review carefully before trading.",
                error=f"{type(e).__name__}: {e}",
            )

        if not _is_complete_language_data(language_data):
            return _stub(
                "Chart was read, but the explanation could not be completed.",
                error="language_json_parse_failed",
                raw=language_raw[:300],
            )
    else:
        language_data = _deterministic_chart_language(provisional_structure, market_state, risk, context)
        timings_ms["language_model_ms"] = 0.0

    assembly_started_at = time.perf_counter()
    merged = _merge_chart_payload(vision_data, language_data, context)
    timings_ms["parse_assembly_ms"] = round((time.perf_counter() - assembly_started_at) * 1000, 2)
    timings_ms["model_ms"] = round(
        timings_ms.get("vision_model_ms", 0.0) + timings_ms.get("language_model_ms", 0.0),
        2,
    )
    timings_ms["total_ms"] = round((time.perf_counter() - total_started_at) * 1000, 2)
    merged["_timings_ms"] = timings_ms
    merged["_analysis_source"] = "gemma_vision_fallback"
    print(
        f"[Multimodal] {OLLAMA_VISION_MODEL} returned {len(raw) + len(language_raw)} chars; "
        f"total={timings_ms['total_ms']:.2f}ms"
    )
    return merged
