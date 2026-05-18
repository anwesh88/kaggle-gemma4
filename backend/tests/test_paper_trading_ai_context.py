from datetime import datetime, timedelta, timezone

from models import Language, TradingContext

import ai_engine
import broker_client
import paper_trading


def test_open_paper_trades_are_visible_to_gemma_context(tmp_path, monkeypatch):
    monkeypatch.setitem(paper_trading.DB_PATHS, "paper", tmp_path / "paper.db")

    paper_trading.reset_db(mode="paper")
    for _ in range(3):
        paper_trading.record_trade(
            "RELIANCE",
            "BUY",
            10,
            1298.40,
            mode="paper",
        )

    trades = paper_trading.get_session_trades_for_ai(mode="paper")

    assert len(trades) == 3
    assert all(t.symbol == "RELIANCE" for t in trades)
    assert all(t.pnl is None for t in trades)
    assert all(not t.is_loss for t in trades)

    ctx = TradingContext(
        recent_trades=trades,
        margin=paper_trading.compute_margin(total=100_000, mode="paper"),
        trading_vows=[
            "I will stop trading after 2 consecutive losses",
            "I will not use more than 50% of my margin",
        ],
        preferred_language=Language.EN,
        source_mode="paper",
    )

    prompt = ai_engine.build_analysis_prompt(ctx)
    thinking_log = ai_engine._build_real_thinking_log(
        ctx,
        score=120,
        risk="low",
        pattern="Healthy Trading",
        nudge="",
        nudge_loc="",
        vows_v=[],
        crisis=0,
        elapsed=12.3,
    )

    assert "Session: 3 trades (0 closed, 3 open)" in prompt
    assert prompt.count("pnl=unrealized OPEN") == 3
    assert "No trades placed yet" not in thinking_log
    assert "Python checked 3 trade(s) (3 open, 0 closed)" in thinking_log


def test_paper_context_includes_current_portfolio_summary(tmp_path, monkeypatch):
    monkeypatch.setitem(paper_trading.DB_PATHS, "paper", tmp_path / "paper.db")

    paper_trading.reset_db(mode="paper")
    paper_trading.record_trade("RELIANCE", "BUY", 10, 100.0, mode="paper")
    paper_trading.record_trade("INFY", "BUY", 5, 200.0, mode="paper")

    ctx = broker_client.get_trading_context(mode="paper")

    assert ctx.open_positions_count == 2
    assert ctx.total_exposure == 2000.0
    assert ctx.exposure_concentration == 0.5
    assert ctx.portfolio_positions == [
        "BUY INFY qty=5 avg=200.0",
        "BUY RELIANCE qty=10 avg=100.0",
    ]

    prompt = ai_engine.build_analysis_prompt(ctx)
    assert "Portfolio: positions BUY INFY qty=5 avg=200.0; BUY RELIANCE qty=10 avg=100.0" in prompt


def test_old_open_paper_trades_remain_visible_to_analysis(tmp_path, monkeypatch):
    monkeypatch.setitem(paper_trading.DB_PATHS, "paper", tmp_path / "paper.db")

    paper_trading.reset_db(mode="paper")
    paper_trading.record_trade("RELIANCE", "BUY", 10, 100.0, mode="paper")

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    with paper_trading.sqlite3.connect(paper_trading._db_path("paper")) as conn:
        conn.execute("UPDATE paper_trades SET timestamp = ?", (old_ts,))

    trades = paper_trading.get_session_trades_for_ai(since_minutes=240, mode="paper")

    assert len(trades) == 1
    assert trades[0].symbol == "RELIANCE"
    assert trades[0].pnl is None
