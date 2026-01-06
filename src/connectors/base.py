import asyncio
import ccxt.async_support as ccxt
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from src.utils.logger import logger
from src.config import Config
from src.models import StandardCandle

# 延迟导入异常类，避免循环导入
# 在需要时动态导入
def _get_exceptions():
    """延迟导入异常类，避免循环导入"""
    try:
        from src.core.exceptions import ExchangeConnectionError, DataFetchError
        return ExchangeConnectionError, DataFetchError
    except ImportError:
        # 如果导入失败，使用通用异常
        return Exception, Exception

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

    async def fetch_ticker(self, symbol: str = None) -> Dict:
        """
        Fetches 24h ticker data.
        """
        target_symbol = self.resolve_symbol(symbol or self.symbol)
        return await self._retry_request(self.exchange.fetch_ticker, target_symbol)

    async def _retry_request(self, func, *args, **kwargs):
        """
        Executes a function with exponential backoff retry logic.
        """
        retries = 3
        initial_delay = 2  # 增加初始延迟
        max_delay = 10     # 最大延迟
        jitter = 0.5       # 随机抖动范围
        
        for attempt in range(retries):
            try:
                return await func(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                # 特别处理429 Too Many Requests错误
                if "429" in str(e) or "Too Many Requests" in str(e):
                    logger.warning(f"[{self.exchange_id}] API限流 (429)，正在重试... (Attempt {attempt+1}/{retries})")
                    # 针对限流错误使用更长的延迟
                    base_delay = initial_delay * (2 ** attempt)
                    # 添加随机抖动，避免请求风暴
                    import random
                    delay = min(base_delay + random.uniform(-jitter, jitter), max_delay)
                    await asyncio.sleep(delay)
                else:
                    logger.warning(f"[{self.exchange_id}] Request failed (Attempt {attempt+1}/{retries}): {e}")
                    # 其他网络错误使用标准指数退避
                    base_delay = initial_delay * (2 ** attempt)
                    delay = min(base_delay, max_delay)
                    await asyncio.sleep(delay)
                    
                if attempt == retries - 1:
                    logger.error(f"[{self.exchange_id}] All retry attempts failed.")
                    # 使用延迟导入的异常类
                    _, DataFetchError = _get_exceptions()
                    raise DataFetchError(f"Failed to fetch data from {self.exchange_id} after {retries} attempts: {e}") from e
            except Exception as e:
                logger.error(f"[{self.exchange_id}] Unexpected error: {e}")
                # 使用延迟导入的异常类
                _, DataFetchError = _get_exceptions()
                raise DataFetchError(f"Unexpected error in {self.exchange_id}: {e}") from e

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
        except (AttributeError, KeyError, TypeError):
            return False
