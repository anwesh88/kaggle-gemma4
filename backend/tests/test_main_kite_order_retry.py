import pytest

import main
import kite_client


@pytest.mark.asyncio
async def test_kite_order_retries_explicit_amo_after_conversion_failure(monkeypatch):
    calls: list[str] = []

    async def fake_place_order(**kwargs):
        calls.append(kwargs["variety"])
        if kwargs["variety"] == "regular":
            raise RuntimeError("Your order could not be converted to a After Market Order (AMO).")
        return {"order_id": "AMO-1"}

    monkeypatch.setattr(kite_client, "place_order", fake_place_order)

    result, variety = await main._place_kite_order_with_amo_retry(
        session_id="sid",
        symbol="RELIANCE",
        quantity=1,
        price=0.0,
        transaction_type="BUY",
        order_type="MARKET",
    )

    assert result == {"order_id": "AMO-1"}
    assert variety == "amo"
    assert calls == ["regular", "amo"]
