import base64
import io

import pytest
from PIL import Image, ImageDraw

import multimodal_engine


def test_preprocess_image_resizes_and_normalizes():
    src = io.BytesIO()
    Image.new("RGB", (2400, 1200), "white").save(src, format="JPEG")

    out = multimodal_engine.preprocess_image_bytes(src.getvalue(), max_edge=1024)
    with Image.open(io.BytesIO(out)) as image:
        assert max(image.size) <= 1024
        assert image.format == "PNG"


def _synthetic_chart(points: list[tuple[int, int]]) -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.line((36, 320, 610, 320), fill="black", width=2)
    draw.line((36, 32, 36, 320), fill="black", width=2)
    draw.line(points, fill="#2563EB", width=5)
    image.save(out, format="PNG")
    return out.getvalue()


def test_chart_fast_path_detects_clear_uptrend():
    data, confidence, meta = multimodal_engine._heuristic_chart_vision_from_bytes(
        _synthetic_chart([
            (48, 300), (120, 280), (190, 250), (260, 220),
            (330, 185), (400, 145), (470, 100), (540, 60), (600, 30),
        ])
    )

    assert data is not None
    assert data["trend"] == "up"
    assert data["momentum"] in {"strong", "weakening"}
    assert data["volatility"] in {"low", "normal"}
    assert confidence >= multimodal_engine.CHART_FAST_PATH_MIN_CONFIDENCE
    assert meta["coverage"] > 0.10


@pytest.mark.asyncio
async def test_chart_fast_path_skips_gemma_for_clear_chart(monkeypatch):
    async def fail_generate(*args, **kwargs):
        raise AssertionError("Gemma fallback should not run for a clear chart")

    monkeypatch.setattr(multimodal_engine, "_generate_chart_vision_json", fail_generate)
    b64 = base64.b64encode(_synthetic_chart([
        (48, 300), (120, 280), (190, 250), (260, 220),
        (330, 185), (400, 145), (470, 100), (540, 60), (600, 30),
    ])).decode()

    result = await multimodal_engine.analyze_chart_full(b64)

    assert result["_analysis_source"] == "deterministic_chart_fast_path"
    assert result["_timings_ms"]["model_ms"] == 0.0
    assert result["market_structure"]["trend"] == "up"


@pytest.mark.asyncio
async def test_chart_retry_on_incomplete_json(monkeypatch):
    calls: list[bool] = []

    async def fake_generate(prompt: str, image_b64: str, *, retry: bool = False):
        calls.append(retry)
        if not retry:
            return ({"trend": "up"}, 0.1, "{}")
        return ({
            "trend": "up",
            "momentum": "strong",
            "volatility": "normal",
        }, 0.2, "{}")

    async def fake_language(prompt: str, *, retry: bool = False):
        return ({
            "personalized_insight": "This resembles your stronger trend-following setups.",
            "behavioral_warning": "Do not chase the move if your planned entry is already gone.",
        }, 0.05, "{}")

    monkeypatch.setattr(multimodal_engine, "_generate_chart_vision_json", fake_generate)
    monkeypatch.setattr(multimodal_engine, "_generate_chart_language_json", fake_language)
    monkeypatch.setattr(multimodal_engine, "CHART_FAST_PATH_ENABLED", False)
    result = await multimodal_engine.analyze_chart_full("ZmFrZQ==")

    assert calls == [False, True]
    assert result["market_state"] == "trending"
    assert result["behavioral_risk"]["fomo_probability"] > 0
    assert result["decision_quality"]["rating"] in {"good", "average", "poor"}


def test_chart_schema_preserved_after_deterministic_assembly():
    merged = multimodal_engine._merge_chart_payload(
        {
            "trend": "sideways",
            "momentum": "weakening",
            "volatility": "low",
        },
        {
            "personalized_insight": "This is calmer than your usual impulsive entries.",
            "behavioral_warning": "Wait for confirmation instead of forcing a trade.",
        },
        {"recent_trades": [], "loss_streak": 0, "dna": {}},
    )

    assert set(merged) >= {
        "market_state",
        "market_structure",
        "behavioral_risk",
        "decision_quality",
        "personalized_insight",
        "behavioral_warning",
    }
    assert set(merged["market_structure"]) == {
        "trend", "momentum", "volatility", "volume_confirmation", "key_observation"
    }
    assert set(merged["behavioral_risk"]) >= {
        "fomo_probability", "revenge_probability", "panic_probability",
        "overconfidence_risk", "emotional_risk_level", "primary_concern"
    }
    assert set(merged["decision_quality"]) == {
        "score", "rating", "entry_timing", "risk_reward", "stop_placement", "position_sizing"
    }
