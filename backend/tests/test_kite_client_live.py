from datetime import datetime, timezone

import kite_client


def test_extract_request_token_from_full_url():
    url = "https://127.0.0.1/?request_token=ABC123XYZ&action=login&status=success"
    assert kite_client.extract_request_token(url) == "ABC123XYZ"


def test_redirect_diagnostics_warns_on_127_hosts():
    diag = kite_client.redirect_diagnostics("http://127.0.0.1:8000/")
    assert diag["expected_redirect_url"].endswith("/kite/callback")
    assert diag["warning"]
    assert "localhost" in diag["warning"]


def test_to_iso_never_leaks_unparseable_trade_timestamp():
    normalized = kite_client._to_iso("bad-broker-date")

    assert normalized != "bad-broker-date"
    assert datetime.fromisoformat(normalized).tzinfo is not None


def test_kite_trades_to_finsight_derives_fifo_realized_pnl():
    raw_trades = [
        {
            "trade_id": "T1",
            "order_id": "O1",
            "tradingsymbol": "RELIANCE",
            "transaction_type": "BUY",
            "quantity": 10,
            "average_price": 100.0,
            "trade_timestamp": datetime(2026, 5, 10, 9, 15, tzinfo=timezone.utc),
        },
        {
            "trade_id": "T2",
            "order_id": "O2",
            "tradingsymbol": "RELIANCE",
            "transaction_type": "SELL",
            "quantity": 4,
            "average_price": 90.0,
            "trade_timestamp": datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc),
        },
        {
            "trade_id": "T3",
            "order_id": "O3",
            "tradingsymbol": "RELIANCE",
            "transaction_type": "SELL",
            "quantity": 6,
            "average_price": 120.0,
            "trade_timestamp": datetime(2026, 5, 10, 9, 45, tzinfo=timezone.utc),
        },
    ]

    normalized = kite_client.kite_trades_to_finsight(raw_trades)

    assert normalized[0]["realized_pnl"] is None
    assert normalized[1]["realized_pnl"] == -40.0
    assert normalized[1]["is_loss"] is True
    assert normalized[2]["realized_pnl"] == 120.0
    assert normalized[2]["is_loss"] is False


def test_build_account_snapshot_exposes_summary_and_positions():
    raw_margins = {
        "equity": {
            "available": {"live_balance": 75000, "opening_balance": 100000},
            "utilised": {"debits": 25000, "m2m_realised": -500},
        }
    }
    raw_holdings = [
        {
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "quantity": 5,
            "average_price": 1400,
            "last_price": 1450,
            "pnl": 250,
            "day_change_percentage": 1.2,
        }
    ]
    raw_positions = {
        "net": [
            {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "product": "MIS",
                "quantity": 10,
                "average_price": 100,
                "pnl": -300,
                "m2m": -300,
            }
        ]
    }
    raw_trades = [
        {
            "trade_id": "T1",
            "order_id": "O1",
            "tradingsymbol": "RELIANCE",
            "transaction_type": "BUY",
            "quantity": 10,
            "average_price": 100.0,
            "trade_timestamp": datetime(2026, 5, 10, 9, 15, tzinfo=timezone.utc),
        }
    ]
    raw_quotes = {
        "NSE:RELIANCE": {"last_price": 98, "ohlc": {"close": 100}, "volume": 1000},
        "NSE:INFY": {"last_price": 1450, "ohlc": {"close": 1430}, "volume": 800},
    }

    snapshot = kite_client.build_account_snapshot(
        raw_margins,
        raw_holdings,
        raw_positions,
        raw_trades,
        raw_quotes,
        watchlist_instruments=["NSE:RELIANCE", "NSE:INFY"],
        warnings=[],
    )

    assert snapshot["margins"]["available_cash"] == 75000
    assert snapshot["summary"]["open_positions_count"] == 1
    assert snapshot["summary"]["holdings_count"] == 1
    assert snapshot["summary"]["open_pnl"] == -300.0
    assert snapshot["holdings"][0]["exposure"] == 7250.0
    assert snapshot["summary"]["total_exposure"] == 8250.0
    assert round(snapshot["summary"]["exposure_concentration"], 4) == 0.8788
    assert snapshot["watchlist"][0]["symbol"] == "NSE:RELIANCE"
