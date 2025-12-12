from typing import List, Dict
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger
from src.config import Config
import time

class OKXConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('okx')

    async def fetch_standard_candles(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List[StandardCandle]:
        target_symbol = symbol or self.symbol
        try:
            # 1. Fetch OHLCV for price/volume structure
            candles_data = await self.fetch_ohlcv(target_symbol, limit=limit)
            
            # 2. Fetch Trades for Taker Volume Approximation
            trades = await self.fetch_trades(target_symbol, limit=Config.LIMIT_TRADES)
            
            # Determine timeframe in ms
            tf_map = {'1m': 60000, '5m': 300000, '15m': 900000, '1h': 3600000}
            tf_ms = tf_map.get(self.timeframe, 900000)
            
            # Aggregate trades into candle buckets
            taker_map: Dict[int, Dict[str, float]] = {}
            oldest_trade_ts = None
            
            for t in trades:
                ts = t['timestamp']
                if oldest_trade_ts is None or ts < oldest_trade_ts:
                    oldest_trade_ts = ts
                    
                candle_ts = (ts // tf_ms) * tf_ms
                
                if candle_ts not in taker_map:
                    taker_map[candle_ts] = {'buy': 0.0, 'sell': 0.0}
                
                # OKX trade structure: side is 'buy' or 'sell' from taker perspective
                cost = t['cost']  # Quote volume (USDT)
                if t['side'] == 'buy':
                    taker_map[candle_ts]['buy'] += cost
                else:
                    taker_map[candle_ts]['sell'] += cost
            
            # Build StandardCandle list
            candles = []
            for ohlcv in candles_data:
                ts = int(ohlcv[0])
                candle_ts = (ts // tf_ms) * tf_ms
                
                # Check if we have trade data for this candle
                if candle_ts in taker_map:
                    taker_buy = taker_map[candle_ts]['buy']
                    taker_sell = taker_map[candle_ts]['sell']
                elif oldest_trade_ts and ts < oldest_trade_ts:
                    # Candle is older than our trade history
                    taker_buy = None
                    taker_sell = None
                else:
                    # No trades in this candle (low activity)
                    taker_buy = 0.0
                    taker_sell = 0.0
                
                candles.append(StandardCandle(
                    timestamp=ts,
                    open=float(ohlcv[1]),
                    high=float(ohlcv[2]),
                    low=float(ohlcv[3]),
                    close=float(ohlcv[4]),
                    volume=float(ohlcv[5]),
                    taker_buy_volume=taker_buy,
                    taker_sell_volume=taker_sell,
                    quote_volume=float(ohlcv[5]) * float(ohlcv[4]),  # Approximate
                    volume_type='quote',
                    exchange_id=self.exchange_id
                ))
            
            return candles
        except Exception as e:
            logger.error(f"OKX fetch failed: {e}")
            return []
