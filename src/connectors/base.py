import asyncio
import ccxt.async_support as ccxt
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from src.utils.logger import logger
from src.config import Config
from src.models import StandardCandle

class ExchangeConnector(ABC):
    """
    Abstract base class for exchange connectors using CCXT async support.
    """
    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.exchange: Optional[ccxt.Exchange] = None
        self.symbol = Config.SYMBOL
        self.timeframe = Config.TIMEFRAME

    @abstractmethod
    async def fetch_standard_candles(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List['StandardCandle']:
        """
        Fetches candles standardized to the internal model.
        """
        pass

    async def initialize(self):
        """
        Initializes the CCXT exchange instance.
        """
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({
                'enableRateLimit': True,
                'timeout': 10000,
                'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            # Load markets to ensure symbol validity
            await self.exchange.load_markets()
            logger.info(f"Initialized {self.exchange_id} connector.")
        except Exception as e:
            logger.error(f"Failed to initialize {self.exchange_id}: {e}")
            raise

    async def close(self):
        """
        Closes the exchange connection.
        """
        if self.exchange:
            await self.exchange.close()
            logger.info(f"Closed {self.exchange_id} connection.")

    async def fetch_ohlcv(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List[Any]:
        """
        Fetches OHLCV data with retry logic.
        """
        target_symbol = self.resolve_symbol(symbol or self.symbol)
        return await self._retry_request(self.exchange.fetch_ohlcv, target_symbol, self.timeframe, limit=limit)

    async def fetch_candles_timeframe(self, symbol: str = None, timeframe: str = '1m', limit: int = 100) -> List[Any]:
        """
        Fetches OHLCV data for a specific timeframe (for multi-timeframe analysis).
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string ('1m', '5m', '1h', etc.)
            limit: Number of candles to fetch
            
        Returns:
            List of OHLCV candles
        """
        target_symbol = self.resolve_symbol(symbol or self.symbol)
        return await self._retry_request(self.exchange.fetch_ohlcv, target_symbol, timeframe, limit=limit)

    async def fetch_trades(self, symbol: str = None, limit: int = Config.LIMIT_TRADES) -> List[Dict]:

        """
        Fetches recent trades with retry logic.
        """
        target_symbol = self.resolve_symbol(symbol or self.symbol)
        return await self._retry_request(self.exchange.fetch_trades, target_symbol, limit=limit)

    async def _retry_request(self, func, *args, **kwargs):
        """
        Executes a function with exponential backoff retry logic.
        """
        retries = 3
        delay = 1
        for attempt in range(retries):
            try:
                return await func(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                logger.warning(f"[{self.exchange_id}] Request failed (Attempt {attempt+1}/{retries}): {e}")
                if attempt == retries - 1:
                    logger.error(f"[{self.exchange_id}] All retry attempts failed.")
                    raise
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as e:
                logger.error(f"[{self.exchange_id}] Unexpected error: {e}")
                raise

    def resolve_symbol(self, symbol: str) -> str:
        """
        Resolve or remap symbol for exchange-specific quirks.
        Default: return original symbol.
        """
        return symbol

    def is_supported_symbol(self, symbol: str) -> bool:
        resolved = self.resolve_symbol(symbol)
        try:
            return bool(self.exchange and resolved in self.exchange.symbols)
        except Exception:
            return False
