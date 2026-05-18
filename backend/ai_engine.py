"""
ai_engine.py — Gemma 4 behavioral analysis engine.

Features used:
  1. Auditable analysis trace — post-inference evidence summary
  2. Structured JSON output — strict schema
  3. Multi-language generation — Hindi/English/Telugu/Tamil nudges
  4. Vow-aware analysis — identity contract checking
  5. Session stress scoring — elevated-risk context tracking
  6. Historical context — from BehavioralDNA

CPU-optimized for i7-1255U (8 threads, no GPU). Defaults to gemma4:e2b
(smaller, ~2x faster on CPU than e4b) with a compressed prompt and a
shorter num_predict. Override OLLAMA_MODEL=gemma4:e4b if you'd rather
trade latency for slightly better generation quality.

The model is pre-warmed once at server startup (see main.py lifespan)
so the first user request doesn't pay the cold-start weight-loading
penalty. With pre-warming, target real-Gemma latency on i7-1255U is
20-40s; without it, first call is ~60-80s.
"""

import os, json, re, time, asyncio
from typing import AsyncIterator
from models import TradingContext, BehavioralAnalysis

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")
OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "90"))

# ── Inference options ────────────────────────────────────────────────────────
#
# Defaults tuned for CPU inference on a 4-year-old i7-1255U / 16 GB. Every
# value is overridable via env so cloud GPU deployments can use bigger
# context, more predict tokens, more GPU layers, etc., without code changes.
#
# Recommended overrides for an A10 / A100 / T4 GPU instance:
#     OLLAMA_NUM_CTX=2048
#     OLLAMA_NUM_PREDICT=400
#     OLLAMA_NUM_GPU=99           # offload all layers to GPU
#     OLLAMA_KEEP_ALIVE=30m       # don't unload between requests
#     OLLAMA_TIMEOUT_S=30         # GPU inference completes in <10s
#
# See docs/gpu-setup.md for full RunPod / Modal / Colab deployment recipes.

def _i(key: str, default: int) -> int:
    try: return int(os.getenv(key, default))
    except (TypeError, ValueError): return default

def _f(key: str, default: float) -> float:
    try: return float(os.getenv(key, default))
    except (TypeError, ValueError): return default


OLLAMA_OPTIONS = {
    "temperature":    _f("OLLAMA_TEMPERATURE", 0.1),
    "num_predict":    _i("OLLAMA_NUM_PREDICT", 200),
    "num_ctx":        _i("OLLAMA_NUM_CTX",     768),
    "num_thread":     _i("OLLAMA_NUM_THREAD",  8),
    "num_gpu":        _i("OLLAMA_NUM_GPU",     0),     # 0 = pure CPU; 99 = all layers on GPU
    "top_p":          _f("OLLAMA_TOP_P",       0.9),
    "repeat_penalty": _f("OLLAMA_REPEAT_PENALTY", 1.05),
}

# How long Ollama keeps the model loaded after the last request. 5m default
# means the next request after a 5-minute idle pays cold-start. On a GPU
# instance with bursty traffic, set "30m" or "-1" (forever).
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")


def _extract_json_object(raw: str) -> dict | None:
    """
    Find and parse the first complete JSON object in `raw`.

    Robust to leading/trailing prose, multiple `{}` constructs, escaped
    quotes, and string literals that contain braces. Stops at the first
    fully-balanced object — we don't want to greedy-match into garbage.
    """
    start = raw.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(raw)):
        c = raw[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None  # never balanced — output was truncated mid-object

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "te": "Telugu", "ta": "Tamil"}


def build_analysis_prompt(ctx: TradingContext) -> str:
    """
    Compressed prompt tuned for CPU inference. Keeps the structured analysis
    contract intact while cutting ~200 tokens of verbose instructions that the
    model didn't need.
    """
    losses = [t for t in ctx.recent_trades if t.is_loss]
    loss_count = len(losses)
    total_loss = sum(t.pnl for t in losses if t.pnl is not None)
    closed_count = sum(1 for t in ctx.recent_trades if t.pnl is not None)
    open_count = max(0, len(ctx.recent_trades) - closed_count)
    margin_pct = round(ctx.margin.usage_ratio * 100, 1)
    lang_name  = LANG_NAMES.get(ctx.preferred_language.value, "English")

    def _trade_line(t) -> str:
        if t.pnl is None:
            pnl_text = "pnl=unrealized"
            outcome = "OPEN"
        else:
            pnl_text = f"pnl=Rs.{t.pnl:.0f}"
            outcome = "LOSS" if t.is_loss else "WIN"
        return (
            f"[{t.timestamp.strftime('%H:%M')}] {t.action} {t.symbol} "
            f"qty={t.quantity} @ Rs.{t.price:.2f} {pnl_text} {outcome}"
        )

    trade_lines = "\n".join(
        _trade_line(t)
        for t in ctx.recent_trades[-5:]   # cap at 5 most recent
    ) or "(none)"
    vow_lines = "\n".join(f"V{i+1}: {v}" for i, v in enumerate(ctx.trading_vows)) or "(none)"

    hist = ""
    if ctx.historical_sessions > 0:
        hist = (f"\nHISTORY: {ctx.historical_sessions} past sessions, "
                f"high-risk rate {ctx.historical_loss_rate*100:.0f}% "
                f"(persistent pattern INCREASES score).")

    live_block = ""
    if ctx.source_mode == "kite":
        notes = "; ".join(ctx.analysis_notes[:3]) if ctx.analysis_notes else "none"
        realized_text = (
            f"₹{ctx.day_realized_pnl:.0f} ({ctx.realized_pnl_source})"
            if ctx.day_realized_pnl is not None
            else f"unknown ({ctx.realized_pnl_source})"
        )
        open_text = (
            f"₹{ctx.open_pnl:.0f} ({ctx.open_pnl_source})"
            if ctx.open_pnl is not None
            else f"unknown ({ctx.open_pnl_source})"
        )
        live_block = f"""

LIVE ACCOUNT CONTEXT
Day realized P&L: {realized_text}
Open P&L / M2M: {open_text}
Open positions: {ctx.open_positions_count}
Holdings: {ctx.holdings_count}
Largest exposure concentration: {ctx.exposure_concentration*100:.0f}%
Inferred loss streak: {ctx.inferred_loss_streak}
Snapshot notes: {notes}
"""

    return f"""You are Finsight OS, a behavioral guardian for self-directed market participants in India. In SEBI's FY2024-25 derivatives study, 91% of individual F&O traders lost money. Detect emotional patterns and intervene.

DATA
Trades this session: {len(ctx.recent_trades)} ({closed_count} closed, {open_count} open)
Closed losses this session: {loss_count} | Realized loss: Rs.{total_loss:.0f}
Margin used: {margin_pct}%{' [DANGER >70%]' if margin_pct > 70 else ''}

TRADES (chronological)
{trade_lines}

VOWS (user's identity contract)
{vow_lines}{hist}{live_block}

Reason internally before answering:
- Which vows are violated?
- Pattern: one of "Revenge Trading" | "FOMO" | "Over-Leveraging" | "Addiction Loop" | "Panic Selling" | "Healthy Trading".
- Score 0-1000: +200 if 2+ losses/hr, +200 if 4+ losses, +150 if margin>70%, +200 per vow violated, +150 if historical risk>50%, -100 if last was a win. Cap 1000.
- In live Kite mode, use negative realized P&L, negative open P&L, 2+ inferred loss streak, and >50% exposure concentration as direct risk evidence.
- If a live P&L source is "derived", treat it as medium-confidence evidence and cross-check it against margin use, concentration, and open risk before deciding.
- Nudge (only if score>600): EXACTLY 15 words, first person, names the pattern, emotionally resonant. Example: "I am trading to recover losses, not following my plan today."
- Local nudge: translate into {lang_name}, keep natural.
- Session stress 0-100: emotional and exposure stress severity.

Reply with ONLY this JSON object — no prose before or after, no markdown:
{{
  "behavioral_score": <0-1000 integer>,
  "risk_level": "<low|medium|high>",
  "detected_pattern": "<one of the 6 patterns>",
  "nudge_message": "<15 words English, or empty if score<=600>",
  "nudge_message_local": "<same nudge in {lang_name}, or empty>",
  "vows_violated": ["<vow text>"],
  "crisis_score": <0-100 integer>
}}"""


def _context_counts(ctx: TradingContext) -> tuple[int, int, int, int, float, float]:
    closed_count = sum(1 for t in ctx.recent_trades if t.pnl is not None)
    open_count = max(0, len(ctx.recent_trades) - closed_count)
    loss_count = sum(1 for t in ctx.recent_trades if t.is_loss)
    total_loss = sum(t.pnl for t in ctx.recent_trades if t.is_loss and t.pnl is not None)
    margin_pct = round(ctx.margin.usage_ratio * 100, 1)
    return len(ctx.recent_trades), closed_count, open_count, loss_count, total_loss, margin_pct


def _format_trade_evidence(ctx: TradingContext, limit: int = 3) -> str:
    lines = []
    for t in ctx.recent_trades[-limit:]:
        if t.pnl is None:
            result = "OPEN unrealized"
        else:
            result = f"{'LOSS' if t.is_loss else 'WIN'} pnl=Rs.{t.pnl:.0f}"
        lines.append(
            f"{t.action} {t.symbol} qty={t.quantity} @ Rs.{t.price:.2f} {result}"
        )
    return "; ".join(lines) if lines else "no trades in context"


def _live_evidence(ctx: TradingContext) -> str:
    if ctx.source_mode != "kite":
        return ""

    realized = (
        f"day realized Rs.{ctx.day_realized_pnl:.0f} ({ctx.realized_pnl_source})"
        if ctx.day_realized_pnl is not None
        else f"day realized unknown ({ctx.realized_pnl_source})"
    )
    open_pnl = (
        f"open P&L Rs.{ctx.open_pnl:.0f} ({ctx.open_pnl_source})"
        if ctx.open_pnl is not None
        else f"open P&L unknown ({ctx.open_pnl_source})"
    )
    return (
        f"; live account: {realized}, {open_pnl}, "
        f"{ctx.open_positions_count} open position(s), "
        f"{ctx.exposure_concentration*100:.0f}% concentration"
    )


def _build_real_thinking_log(
    ctx: TradingContext,
    *,
    score: int,
    risk: str,
    pattern: str,
    nudge: str,
    nudge_loc: str,
    vows_v: list[str],
    crisis: int,
    elapsed: float,
) -> str:
    """Auditable post-inference summary: actual context + actual Gemma JSON."""
    trade_count, closed_count, open_count, loss_count, total_loss, margin_pct = _context_counts(ctx)
    vow_summary = "; ".join(vows_v) if vows_v else "none"
    nudge_preview = nudge if nudge else "none - score below intervention threshold"
    local_status = "yes" if nudge_loc else "not needed"

    return "\n".join([
        f"Real Gemma 4 inference - {elapsed:.1f}s on {OLLAMA_MODEL}",
        (
            "STEP 1 - VOW CHECK: "
            f"Gemma received {trade_count} trade(s) ({open_count} open, {closed_count} closed) "
            f"and {len(ctx.trading_vows)} vow(s); violated: {vow_summary}."
        ),
        (
            "STEP 2 - PATTERN: "
            f"Gemma selected {pattern}. Trade evidence: {_format_trade_evidence(ctx)}."
        ),
        (
            "STEP 3 - SCORE: "
            f"{score}/1000 ({risk}); {loss_count} closed loss(es), "
            f"realized loss Rs.{total_loss:.0f}, margin {margin_pct}%{_live_evidence(ctx)}."
        ),
        f"STEP 4 - NUDGE: {nudge_preview}.",
        f"STEP 5 - LANGUAGE: local-language nudge {local_status}.",
        (
            "STEP 6 - STRESS: "
            f"{crisis}/100 ({'elevated' if crisis > 70 else 'below threshold'})."
        ),
        "STEP 7 - SEBI: disclosure grounded by ChromaDB RAG and attached server-side.",
    ])


def get_unavailable_analysis(
    ctx: TradingContext | None = None,
    reason: str = "Gemma did not return a usable response",
) -> BehavioralAnalysis:
    """Explicit failure state. Never masquerades as behavioral insight."""
    if ctx is None:
        context_line = "No TradingContext was available for this run."
    else:
        trade_count, closed_count, open_count, loss_count, total_loss, margin_pct = _context_counts(ctx)
        context_line = (
            f"Context available but not analyzed: {trade_count} trade(s) "
            f"({open_count} open, {closed_count} closed), {loss_count} closed loss(es), "
            f"realized loss Rs.{total_loss:.0f}, margin {margin_pct}%."
        )

    thinking_log = "\n".join([
        "Gemma 4 inference unavailable - no model insight produced",
        f"STEP 1 - CONTEXT: {context_line}",
        f"STEP 2 - STATUS: {reason}.",
        "STEP 3 - SCORE: withheld because Gemma did not complete.",
        "STEP 4 - NUDGE: withheld because Gemma did not complete.",
        "STEP 5 - LANGUAGE: withheld because Gemma did not complete.",
        "STEP 6 - STRESS: withheld because Gemma did not complete.",
        "STEP 7 - SEBI: disclosure not attached to a completed model analysis.",
    ])

    return BehavioralAnalysis(
        behavioral_score=0,
        risk_level="low",
        detected_pattern="Gemma unavailable",
        nudge_message="",
        nudge_message_local="",
        vows_violated=[],
        crisis_score=0,
        crisis_detected=False,
        sebi_disclosure=None,
        thinking_log=thinking_log,
        inference_seconds=None,
    )


async def warm_up_model() -> None:
    """
    Run a tiny inference at startup so the FIRST user request doesn't pay
    the 10-30s weight-loading cold start. Called from main.py lifespan.
    Silent on success; logs but never raises on failure.
    """
    try:
        import ollama
        print(f"[Finsight AI] Pre-warming {OLLAMA_MODEL}...", flush=True)
        t = time.time()
        await asyncio.wait_for(
            ollama.AsyncClient(host=OLLAMA_HOST).generate(
                model=OLLAMA_MODEL,
                prompt="Reply with the single word: ready",
                options={
                    "num_predict": 4, "num_ctx": 64, "temperature": 0.0,
                    "num_thread": OLLAMA_OPTIONS["num_thread"],
                    "num_gpu":    OLLAMA_OPTIONS["num_gpu"],
                },
                keep_alive=OLLAMA_KEEP_ALIVE,
            ),
            timeout=60.0,
        )
        print(f"[Finsight AI] Pre-warm complete in {time.time() - t:.1f}s", flush=True)
    except Exception as e:
        print(f"[Finsight AI] Pre-warm skipped ({type(e).__name__}: {e}) — first request will pay cold start", flush=True)


async def analyze_behavior(ctx: TradingContext) -> BehavioralAnalysis:
    import ollama

    prompt = build_analysis_prompt(ctx)

    runtime_label = "GPU" if OLLAMA_OPTIONS["num_gpu"] > 0 else "CPU"
    print("\n" + "="*60)
    print(f"[Finsight AI] Running {OLLAMA_MODEL} locally ({runtime_label})...")
    print("="*60)

    start = time.time()

    # Use Ollama's `format=json` mode — forces structured output and prevents
    # the e2b CPU path from emitting 0 chars when sampling stalls. Also
    # widen num_ctx if the prompt is bigger than the configured budget,
    # otherwise the model silently truncates and returns nothing.
    approx_tokens = len(prompt) // 4 + 32
    runtime_options = {
        **OLLAMA_OPTIONS,
        "num_ctx": max(OLLAMA_OPTIONS.get("num_ctx", 768), approx_tokens + 256),
        # E2B occasionally bails after a single empty token at low predict
        # budgets — give it room to actually emit the JSON.
        "num_predict": max(OLLAMA_OPTIONS.get("num_predict", 200), 384),
        # Stop sequences that often appear after the model finishes the JSON
        # cleanly (prevents trailing prose that confuses the JSON extractor).
        "stop": ["\n\n\n", "</s>", "<end>"],
    }
    try:
        response = await asyncio.wait_for(
            ollama.AsyncClient(host=OLLAMA_HOST).generate(
                model=OLLAMA_MODEL,
                prompt=prompt,
                options=runtime_options,
                format="json",                  # forces JSON output, fixes 0-char bug
                keep_alive=OLLAMA_KEEP_ALIVE,
            ),
            timeout=OLLAMA_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        print(f"[Finsight AI] Timeout after {OLLAMA_TIMEOUT_S}s - no model insight produced")
        return get_unavailable_analysis(ctx, f"Timed out after {OLLAMA_TIMEOUT_S}s")
    except Exception as e:
        print(f"[Finsight AI] Ollama error: {type(e).__name__}: {e} - no model insight produced")
        return get_unavailable_analysis(ctx, f"Ollama error: {type(e).__name__}: {e}")

    elapsed = time.time() - start
    raw = response["response"]
    print(f"[Finsight AI] Inference: {elapsed:.2f}s ({len(raw)} chars)")

    # Brace-balanced JSON extractor — robust to prose around the JSON, to
    # multiple {} constructs in the same response, and to nested objects.
    data = _extract_json_object(raw)

    if data is None:
        print(f"[Finsight AI] JSON parse failed — raw response (first 600 chars):")
        print(repr(raw[:600]))
        print(f"[Finsight AI] No model insight produced")
        return get_unavailable_analysis(ctx, "Gemma returned non-JSON output")

    # Pull fields with defaults
    score      = int(data.get("behavioral_score", 800))
    risk       = data.get("risk_level", "high")
    pattern    = data.get("detected_pattern", "Revenge Trading")
    nudge      = data.get("nudge_message", "")
    nudge_loc  = data.get("nudge_message_local", "")
    vows_v     = data.get("vows_violated", []) or []
    crisis     = int(data.get("crisis_score", 0))

    thinking_log = _build_real_thinking_log(
        ctx,
        score=score,
        risk=risk,
        pattern=pattern,
        nudge=nudge,
        nudge_loc=nudge_loc,
        vows_v=[str(v) for v in vows_v],
        crisis=crisis,
        elapsed=elapsed,
    )

    # Console log for technical verification
    print("\n" + "="*60)
    print("[GEMMA AUDIT TRACE — Technical Verification]")
    print("="*60)
    print(thinking_log)
    print("="*60 + "\n")

    return BehavioralAnalysis(
        behavioral_score=score,
        risk_level=risk,
        detected_pattern=pattern,
        nudge_message=nudge,
        nudge_message_local=nudge_loc,
        vows_violated=vows_v,
        crisis_score=crisis,
        crisis_detected=crisis > 70,
        sebi_disclosure="",     # overwritten by RAG in main.py
        thinking_log=thinking_log,
        inference_seconds=round(elapsed, 2),
    )


# ── Streaming variant ─────────────────────────────────────────────────────────
#
# Yields {type, ...} dicts that the SSE endpoint serializes onto the wire.
# Three event types:
#   "status"  — meta (e.g. "sending context", "still analyzing")
#   "token"   — incremental thinking-log text the UI types out live
#   "result"  — the final BehavioralAnalysis (analysis.model_dump())


async def analyze_behavior_stream(ctx: TradingContext) -> AsyncIterator[dict]:
    """
    Stream only real Gemma-derived analysis.

    Earlier builds streamed a synthetic demo thinking log while Gemma was
    running. That made successful paper/live runs look fake because the UI
    could show "No trades placed yet" even when the final model response used
    real context. This stream now sends status heartbeats while Gemma runs,
    then emits the final audit log built from the actual context plus Gemma's
    structured JSON response. If Gemma fails, the result says unavailable
    explicitly instead of inventing behavioral insight.
    """
    trade_count, closed_count, open_count, _, _, margin_pct = _context_counts(ctx)
    yield {
        "type": "status",
        "message": (
            f"Sending {trade_count} trade(s) ({open_count} open, {closed_count} closed), "
            f"{len(ctx.trading_vows)} vow(s), margin {margin_pct}% to {OLLAMA_MODEL}"
        ),
    }

    start_t = time.time()
    real_task: asyncio.Task[BehavioralAnalysis] = asyncio.create_task(
        asyncio.wait_for(analyze_behavior(ctx), timeout=OLLAMA_TIMEOUT_S + 5)
    )

    try:
        while not real_task.done():
            await asyncio.sleep(5.0)
            if not real_task.done():
                elapsed = time.time() - start_t
                yield {
                    "type": "status",
                    "message": (
                        f"Gemma still analyzing real trade context "
                        f"({elapsed:.0f}s, {trade_count} trade(s) sent)"
                    ),
                }
    except asyncio.CancelledError:
        real_task.cancel()
        raise

    try:
        analysis = await real_task
        elapsed = time.time() - start_t
        print(f"[Finsight AI] Stream done: real Gemma in {elapsed:.2f}s, "
              f"score={analysis.behavioral_score}")
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
        print(f"[Finsight AI] Stream done: unavailable ({type(e).__name__}: {e})")
        analysis = get_unavailable_analysis(ctx, f"Stream failed: {type(e).__name__}: {e}")

    if analysis.thinking_log:
        for line in analysis.thinking_log.split("\n"):
            if line.strip():
                yield {"type": "token", "text": line + "\n"}
                await asyncio.sleep(0.02)

    yield {"type": "result", "analysis": analysis.model_dump()}
