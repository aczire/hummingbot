import logging
from typing import Any, Dict, List, Optional

from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.data_feed.candles_feed.dydx_v4_perpetual_candles import constants as CONSTANTS
from hummingbot.data_feed.candles_feed.candles_base import CandlesBase
from hummingbot.logger import HummingbotLogger


class DydxV4PerpetualCandlesBase(CandlesBase):
    """Base class for dYdX v4 perpetual candles with common logic."""

    _logger: Optional[HummingbotLogger] = None
    _domain: str = "dydx_v4_perpetual"  # Override in subclasses
    _rest_url: str = CONSTANTS.REST_URL  # Override in subclasses
    _wss_url: str = CONSTANTS.WSS_URL  # Override in subclasses

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, trading_pair: str, interval: str = "1m", max_records: int = 150):
        super().__init__(trading_pair, interval, max_records)
        self._ping_timeout = None
        # Enable autoping for dYdX WebSocket (server expects pong within 10 seconds)
        self._autoping = True

    @property
    def name(self):
        return f"{self._domain}_{self._trading_pair}"

    @property
    def rest_url(self):
        return self._rest_url

    @property
    def wss_url(self):
        return self._wss_url

    @property
    def health_check_url(self):
        return self.rest_url + CONSTANTS.HEALTH_CHECK_ENDPOINT

    @property
    def candles_url(self):
        return self.rest_url + CONSTANTS.CANDLES_ENDPOINT + "/" + self._ex_trading_pair

    @property
    def candles_endpoint(self):
        return CONSTANTS.CANDLES_ENDPOINT

    @property
    def candles_max_result_per_rest_request(self):
        return CONSTANTS.MAX_RESULTS_PER_CANDLESTICK_REST_REQUEST

    @property
    def rate_limits(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def intervals(self):
        return CONSTANTS.INTERVALS

    async def check_network(self) -> NetworkStatus:
        rest_assistant = await self._api_factory.get_rest_assistant()
        await rest_assistant.execute_request(
            url=self.health_check_url, throttler_limit_id=CONSTANTS.HEALTH_CHECK_ENDPOINT
        )
        return NetworkStatus.CONNECTED

    def get_exchange_trading_pair(self, trading_pair):
        # dYdX uses format like "BTC-USD", "ETH-USD"
        return trading_pair.replace("-", "-")

    @property
    def _is_last_candle_not_included_in_rest_request(self):
        return False

    @property
    def _is_first_candle_not_included_in_rest_request(self):
        return False

    def _get_rest_candles_params(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = CONSTANTS.MAX_RESULTS_PER_CANDLESTICK_REST_REQUEST,
    ) -> dict:
        """
        For API documentation, please refer to:
        https://docs.dydx.exchange/api_integration-indexer/indexer_api#getperpetualmarketcandles

        dYdX v4 resolution mapping:
        1MIN, 5MINS, 15MINS, 30MINS, 1HOUR, 4HOURS, 1DAY
        """
        # Map interval to dYdX resolution format
        resolution_map = {
            "1m": "1MIN",
            "5m": "5MINS",
            "15m": "15MINS",
            "30m": "30MINS",
            "1h": "1HOUR",
            "4h": "4HOURS",
            "1d": "1DAY",
        }

        resolution = resolution_map.get(self.interval, "1MIN")

        params = {
            "resolution": resolution,
        }

        if limit:
            params["limit"] = limit

        # dYdX uses ISO 8601 timestamps
        if start_time:
            from datetime import datetime

            params["fromISO"] = datetime.utcfromtimestamp(start_time).isoformat() + "Z"
        if end_time:
            from datetime import datetime

            params["toISO"] = datetime.utcfromtimestamp(end_time).isoformat() + "Z"

        return params

    def _parse_rest_candles(self, data: dict, end_time: Optional[int] = None) -> List[List[float]]:
        """
        Parse dYdX candles response.

        dYdX response format:
        {
          "candles": [
            {
              "startedAt": "2023-01-01T00:00:00.000Z",
              "ticker": "BTC-USD",
              "resolution": "1MIN",
              "low": "16500.0",
              "high": "16600.0",
              "open": "16550.0",
              "close": "16580.0",
              "baseTokenVolume": "10.5",
              "usdVolume": "174090.0",
              "trades": 42,
              "startingOpenInterest": "1000.0",
              "orderbookMidPriceOpen": "16555.0",
              "orderbookMidPriceClose": "16585.0"
            }
          ]
        }
        """
        candles = data.get("candles", [])

        parsed_candles = []
        for candle in candles:
            # Convert ISO timestamp to unix timestamp in seconds
            from dateutil import parser

            timestamp = int(parser.parse(candle["startedAt"]).timestamp())

            # Extract OHLCV data
            open_price = float(candle["open"])
            high_price = float(candle["high"])
            low_price = float(candle["low"])
            close_price = float(candle["close"])
            volume = float(candle["baseTokenVolume"])
            quote_volume = float(candle["usdVolume"])
            n_trades = int(candle.get("trades", 0))

            # dYdX doesn't provide taker buy volumes, use 0 as placeholder
            taker_buy_base_volume = 0.0
            taker_buy_quote_volume = 0.0

            parsed_candles.append(
                [
                    timestamp,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    quote_volume,
                    n_trades,
                    taker_buy_base_volume,
                    taker_buy_quote_volume,
                ]
            )

        # Sort by timestamp (oldest first)
        parsed_candles.sort(key=lambda x: x[0])

        return parsed_candles

    def ws_subscription_payload(self):
        """
        Subscribe to dYdX v4 candles channel.

        WebSocket subscription format:
        {
          "type": "subscribe",
          "channel": "v4_candles",
          "id": "{market}/{resolution}"
        }
        """
        # Map interval to dYdX resolution format
        resolution_map = {
            "1m": "1MIN",
            "5m": "5MINS",
            "15m": "15MINS",
            "30m": "30MINS",
            "1h": "1HOUR",
            "4h": "4HOURS",
            "1d": "1DAY",
        }

        resolution = resolution_map.get(self.interval, "1MIN")

        payload = {"type": "subscribe", "channel": "v4_candles", "id": f"{self._ex_trading_pair}/{resolution}"}
        return payload

    def _parse_websocket_message(self, data):
        """
        Parse dYdX v4 WebSocket candle message.

        WebSocket message format:
        {
          "type": "channel_data",
          "connection_id": "...",
          "message_id": 1,
          "id": "BTC-USD/1MIN",
          "channel": "v4_candles",
          "version": "1.0.0",
          "contents": {
            "startedAt": "2023-01-01T00:00:00.000Z",
            "ticker": "BTC-USD",
            "resolution": "1MIN",
            "low": "16500.0",
            "high": "16600.0",
            "open": "16550.0",
            "close": "16580.0",
            "baseTokenVolume": "10.5",
            "usdVolume": "174090.0",
            "trades": 42
          }
        }
        """
        candles_row_dict: Dict[str, Any] = {}

        if data is not None and data.get("type") == "channel_data" and data.get("channel") == "v4_candles":
            contents = data.get("contents", {})

            if contents:
                # Convert ISO timestamp to unix timestamp in seconds
                from dateutil import parser

                timestamp = int(parser.parse(contents["startedAt"]).timestamp())

                candles_row_dict["timestamp"] = timestamp
                candles_row_dict["open"] = contents["open"]
                candles_row_dict["high"] = contents["high"]
                candles_row_dict["low"] = contents["low"]
                candles_row_dict["close"] = contents["close"]
                candles_row_dict["volume"] = contents["baseTokenVolume"]
                candles_row_dict["quote_asset_volume"] = contents["usdVolume"]
                candles_row_dict["n_trades"] = contents.get("trades", 0)
                candles_row_dict["taker_buy_base_volume"] = 0.0  # Not provided by dYdX
                candles_row_dict["taker_buy_quote_volume"] = 0.0  # Not provided by dYdX

                return candles_row_dict

        # Return None for non-candle messages (subscribed, connected, etc.)
        return None


class DydxV4PerpetualCandles(DydxV4PerpetualCandlesBase):
    """dYdX v4 Perpetual Mainnet candles."""

    _domain = "dydx_v4_perpetual"
    _rest_url = CONSTANTS.REST_URL
    _wss_url = CONSTANTS.WSS_URL


class DydxV4PerpetualTestnetCandles(DydxV4PerpetualCandlesBase):
    """dYdX v4 Perpetual Testnet candles."""

    _domain = "dydx_v4_perpetual_testnet"
    _rest_url = CONSTANTS.REST_URL_TESTNET
    _wss_url = CONSTANTS.WSS_URL_TESTNET
