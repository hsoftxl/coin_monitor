from typing import List, Dict
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger
import time
from src.config import Config

class CoinbaseConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('coinbase')

    async def fetch_standard_candles(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List[StandardCandle]:
        target_symbol = symbol or self.symbol
        try:
            # 1. Fetch OHLCV for price/total volume
            candles_data = await self.fetch_ohlcv(target_symbol, limit=limit)
            
            # 2. Fetch Trades for Taker Volume Approximation
            # Coinbase 'fetch_trades' returns standardized structure.
            # We can only realistically calculate Taker Flow for the VERY RECENT candles (last 1-2).
            # The user accepted this limitation.
            trades = await self.fetch_trades(target_symbol, limit=Config.LIMIT_TRADES)
            
            # Aggregate trades into buckets
            # Timeframe 15m = 900s = 900000ms
            tf_ms = 15 * 60 * 1000
            taker_map: Dict[int, float] = {} # timestamp -> taker_buy_vol
            oldest_trade_ts = float('inf')
            
            for t in trades:
                ts = t['timestamp']
                if ts < oldest_trade_ts:
                    oldest_trade_ts = ts
                bucket = ts - (ts % tf_ms)
                # Coinbase 'side' is usually the taker side. side='buy' -> Taker Buy.
                if t['side'] == 'buy':
                    taker_map[bucket] = taker_map.get(bucket, 0.0) + float(t['amount'])
            
            candles = []
            for k in candles_data:
                # k: [ts, o, h, l, c, vol]
                ts = int(k[0])
                
                # Check coverage
                # The candle end time is ts + tf_ms. The trade needs to be within [ts, ts+tf_ms).
                # If oldest_trade_ts > (ts + tf_ms), we have NO data for this candle.
                # If oldest_trade_ts is inside the candle, we have partial data.
                # Strictly speaking, we should only trust if oldest_trade_ts <= ts.
                
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
                    taker_sell_volume=taker_sell_vol, # Approximation mixing Total Vol (KLine) and Taker (Trades)
                    quote_volume=None, # Coinbase OHLCV relies on base
                    volume_type='base',
                    exchange_id=self.exchange_id
                ))
            return candles
        except Exception as e:
            logger.error(f"Coinbase fetch failed: {e}")
            return []
