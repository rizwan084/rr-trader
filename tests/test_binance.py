from __future__ import annotations

import pytest

from backend.app.clients.binance import BinanceClient


def test_binance_client_base_urls() -> None:
    client = BinanceClient()

    assert client._base_url(
        "futures"
    ).startswith(
        "https://fapi.binance.com"
    )

    assert client._base_url(
        "spot"
    ).startswith(
        "https://api.binance.com"
    )


def test_binance_client_rejects_invalid_market() -> None:
    client = BinanceClient()

    with pytest.raises(
        ValueError,
        match="market must be",
    ):
        client._base_url(
            "invalid"
        )


@pytest.mark.asyncio
async def test_binance_client_can_close() -> None:
    client = BinanceClient()

    await client.close()

    assert client._client is None
