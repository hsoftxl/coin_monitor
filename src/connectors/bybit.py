from typing import List, Dict
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger
from src.config import Config

class BybitConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('bybit')

    async def fetch_standard_candles(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List[StandardCandle]:
        target_symbol = symbol or self.symbol
        try:
            # 1. Fetch OHLCV
            candles_data = await self.fetch_ohlcv(target_symbol, limit=limit)
            
            # 2. Fetch Trades for Taker Volume Approximation
            # Bybit 'fetch_trades' returns standardized structure.
            trades = await self.fetch_trades(target_symbol, limit=Config.LIMIT_TRADES)
            
            tf_ms = 15 * 60 * 1000
            taker_map: Dict[int, float] = {}
            oldest_trade_ts = float('inf')
            
            for t in trades:
                ts = t['timestamp']
                if ts < oldest_trade_ts:
                    oldest_trade_ts = ts
                bucket = ts - (ts % tf_ms)
                if t['side'] == 'buy':
                    taker_map[bucket] = taker_map.get(bucket, 0.0) + float(t['amount'])
            
            candles = []
            for k in candles_data:
                ts = int(k[0])
                
                if ts < oldest_trade_ts:
                    taker_buy = None
                    taker_sell_vol = None
                else:
                    taker_buy = taker_map.get(ts, 0.0)
                    taker_sell_vol = float(k[5]) - taker_buy
                
                candles.append(StandardCandle(
                    timestamp=ts,
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    taker_buy_volume=taker_buy,
                    taker_sell_volume=taker_sell_vol,
                    quote_volume=None,
                    volume_type='base',
                    exchange_id=self.exchange_id
                ))
            return candles
        except Exception as e:
            logger.error(f"Bybit fetch failed: {e}")
            return []
