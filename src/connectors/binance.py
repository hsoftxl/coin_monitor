from typing import List
from src.connectors.base import ExchangeConnector
from src.models import StandardCandle
from src.utils.logger import logger
from src.config import Config # Added import for Config

class BinanceConnector(ExchangeConnector):
    def __init__(self):
        super().__init__('binance')
        
    async def initialize(self):
        """
        Overridden to support Futures options
        """
        import ccxt.async_support as ccxt
        try:
            options = {}
            if Config.MARKET_TYPE == 'future':
                options['defaultType'] = Config.BINANCE_FUTURE_TYPE
                
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'timeout': 10000,
                'options': options,
                'userAgent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            await self.exchange.load_markets()
            logger.info(f"Initialized binance connector (Mode: {Config.MARKET_TYPE})")
        except Exception as e:
            logger.error(f"Failed to initialize binance: {e}")
            raise

    async def fetch_standard_candles(self, symbol: str = None, limit: int = Config.LIMIT_KLINE) -> List[StandardCandle]:
        target_symbol = symbol or self.symbol
        try:
            # Binance: k[9] is Taker Buy Base Asset Volume, k[10] is Taker Buy Quote Asset Volume
            # fetch_ohlcv doesn't return these extra fields usually unless specified?
            # CCXT fetch_ohlcv typically only returns [ts, o, h, l, c, v]. 
            # We need to use `public_get_klines` to get full response or check if ccxt returns it.
            # CCXT might map it or we use raw request. 
            # Using raw request for maximum control as per previous design logic.
            
            market = self.exchange.market(target_symbol)
            params = {
                'symbol': market['id'],
                'interval': self.timeframe,
                'limit': limit
            }
            
            if Config.MARKET_TYPE == 'future':
                # Futures API endpoint
                response = await self.exchange.fapiPublicGetKlines(params)
            else:
                # Spot API endpoint
                response = await self.exchange.public_get_klines(params)
            
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
            # Silently skip invalid symbols (e.g., OKX-specific formats like "COIN/USDT:USDT")
            if "Invalid symbol" in str(e) or "-1121" in str(e):
                return []
            # Log other errors
            logger.error(f"Binance fetch failed: {e}")
            return []
