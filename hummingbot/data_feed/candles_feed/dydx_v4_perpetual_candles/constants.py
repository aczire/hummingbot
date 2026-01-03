from bidict import bidict

from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit

# Mainnet URLs
REST_URL = "https://indexer.dydx.trade"
WSS_URL = "wss://indexer.dydx.trade/v4/ws"

# Testnet URLs
REST_URL_TESTNET = "https://indexer.v4testnet.dydx.exchange"
WSS_URL_TESTNET = "wss://indexer.v4testnet.dydx.exchange/v4/ws"

HEALTH_CHECK_ENDPOINT = "/v4/height"
CANDLES_ENDPOINT = "/v4/candles/perpetualMarkets"

INTERVALS = bidict(
    {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
)

MAX_RESULTS_PER_CANDLESTICK_REST_REQUEST = 100
REQUEST_WEIGHT = "REQUEST_WEIGHT"

# WebSocket ping/pong configuration
# dYdX sends ping every 30 seconds, expects pong within 10 seconds
PING_TIMEOUT = 30.0

RATE_LIMITS = [
    RateLimit(REQUEST_WEIGHT, limit=100, time_interval=10),
    RateLimit(CANDLES_ENDPOINT, weight=1, limit=100, time_interval=10, linked_limits=[LinkedLimitWeightPair("raw", 1)]),
    RateLimit(HEALTH_CHECK_ENDPOINT, limit=100, time_interval=10, linked_limits=[LinkedLimitWeightPair("raw", 1)]),
]
