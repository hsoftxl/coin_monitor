from typing import List
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger

class BinanceConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('binance')

    async def fetch_standard_candles(self, limit: int = 100) -> List[StandardCandle]:
        try:
            # Binance raw klines: [Open time, Open, High, Low, Close, Volume, Close time, Quote volume, Trades, Taker buy base, Taker buy quote, Ignore]
            # Symbol format: ETH/USDT -> ETHUSDT
            symbol = self.symbol.replace('/', '')
            response = await self.exchange.public_get_klines({
                'symbol': symbol,
                'interval': self.timeframe,
                'limit': limit
            })
            
            candles = []
            for k in response:
                # k[9] is Taker Buy Base Asset Volume
                # k[5] is Volume (Total Base)
                # k[7] is Quote Volume
                # k[10] is Taker Buy Quote Asset Volume
                candles.append(StandardCandle(
                    timestamp=int(k[0]),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    taker_buy_volume=float(k[9]),
                    taker_sell_volume=float(k[5]) - float(k[9]), # Total - TakerBuy = TakerSell (approx, assuming all vol is Taker+Maker? No. Volume is all trades. TakerBuy is subset. Volume - TakerBuy = MakerBuy? No.
                    # Taker Buy + Taker Sell = Total Taker? 
                    # Actually Total Volume = Taker Buy + Taker Sell? No. 
                    # Total Volume = Buy + Sell. 
                    # In crypto, every trade has a Buyer and Seller. One is Taker, one is Maker.
                    # "Taker Buy Volume" means the Taker was on the Buy side.
                    # "Volume" is total matched volume.
                    # So Total Volume = (Taker Buy Volume) + (Taker Sell Volume).
                    # Proof: If Taker Buys, Maker Sells. Volume counts once.
                    # If Taker Sells, Maker Buys. Volume counts once.
                    # So Volume = Taker Buy + Taker Sell.
                    # So Taker Sell = Volume - Taker Buy.
                    quote_volume=float(k[7]),
                    volume_type='base',
                    exchange_id=self.exchange_id
                ))
            return candles
        except Exception as e:
            logger.error(f"Binance fetch failed: {e}")
            return []
