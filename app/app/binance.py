import httpx

from app.config import settings


class BinanceClient:
    def __init__(self):
        self.futures_url = settings.binance_futures_url
        self.spot_url = settings.binance_spot_url
        self.timeout = settings.request_timeout

    async def _get(self, url: str, params: dict | None = None):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def futures_tickers(self):
        return await self._get(
            f"{self.futures_url}/fapi/v1/ticker/24hr"
        )

    async def spot_tickers(self):
        return await self._get(
            f"{self.spot_url}/api/v3/ticker/24hr"
        )

    async def futures_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 100,
    ):
        return await self._get(
            f"{self.futures_url}/fapi/v1/klines",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
            },
        )

    async def spot_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 100,
    ):
        return await self._get(
            f"{self.spot_url}/api/v3/klines",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
            },
        )

    async def futures_exchange_info(self):
        return await self._get(
            f"{self.futures_url}/fapi/v1/exchangeInfo"
        )

    async def spot_exchange_info(self):
        return await self._get(
            f"{self.spot_url}/api/v3/exchangeInfo"
        )


binance_client = BinanceClient()
