from typing import List
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger

class OKXConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('okx')

    async def fetch_standard_candles(self, limit: int = 100) -> List[StandardCandle]:
        try:
            # OKX raw candles: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            # Symbol: ETH/USDT -> ETH-USDT (usually)
            symbol = self.symbol.replace('/', '-')
            response = await self.exchange.public_get_market_candles({
                'instId': symbol,
                'bar': self.timeframe,
                'limit': limit
            })
            # OKX returns data usually in reverse chronological order (newest first)? 
            # CCXT usually normalizes. public_get returns raw. 
            # Check API docs: "Data is sorted by time in descending order".
            # We usually want ascending.
            
            data = response.get('data', [])
            candles = []
            for k in reversed(data): # Reverse to ascending
                # volCcyQuote (index 7) is Quote Volume (USDT).
                # OKX Design says: "Use volCcyQuote".
                # But is it Taker? The Design says "Use it".
                # We will map it to volume. 
                # Calculating Taker Buy specifically is not possible from this field alone if it's Total.
                # But we follow the spec.
                # We will set taker_buy_volume as None or maybe 50%?
                # Wait, if we can't get Taker, we can't do "Taker Flow Analysis".
                # The Design says "OKX K-line has volCcyQuote ... Solution: Direct use that value, results in USDT."
                # It lists it under "Exchange Taker Buy Volume Extraction Source".
                # This explicitly implies the user CONSIDERS `volCcyQuote` as the Taker Volume source.
                # It might be a mistake in the user's knowledge, but I must follow "Taker Buy Volume Extraction Source".
                # So I assign `volCcyQuote` to `taker_buy_volume`?
                # Or does it mean calculate from it? 
                # "Taker Buy Volume ... Source: volCcyQuote".
                # I will assign it to `taker_buy_volume`.
                # Note: `volCcyQuote` is usually TOTAL Quote Volume. Assigning it to Taker Buy is weird (implies 100% Taker Buy).
                # But I will follow the "Extraction Source" table instruction literally.
                # Actually, maybe it means "Use this for volume normalization".
                # But the column header is "Taker Buy Volume Extraction Source".
                # I will use it as Taker Buy Volume.
                
                candles.append(StandardCandle(
                    timestamp=int(k[0]),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]), # Base volume
                    taker_buy_volume=float(k[7]), # Using quote volume as requested, treating as 'quote' type
                    taker_sell_volume=0.0, # Cannot deduce
                    quote_volume=float(k[7]),
                    volume_type='quote', # Result is already USDT
                    exchange_id=self.exchange_id
                ))
            return candles
        except Exception as e:
            logger.error(f"OKX fetch failed: {e}")
            return []
