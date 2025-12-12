import asyncio
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OKXConnector
from src.connectors.bybit import BybitConnector
from src.connectors.coinbase import CoinbaseConnector
from src.utils.logger import logger

async def test_connectors():
    connectors = [
        BinanceConnector(),
        OKXConnector(),
        BybitConnector(),
        CoinbaseConnector()
    ]

    for connector in connectors:
        try:
            logger.info(f"Testing {connector.exchange_id}...")
            await connector.initialize()
            
            # Test OHLCV
            ohlcv = await connector.fetch_ohlcv(limit=5)
            logger.info(f"Fetched {len(ohlcv)} OHLCV candles from {connector.exchange_id}")
            if ohlcv:
                logger.info(f"Sample Candle: {ohlcv[0]}")
            
            # Test Trades (Important for Coinbase)
            trades = await connector.fetch_trades(limit=5)
            logger.info(f"Fetched {len(trades)} trades from {connector.exchange_id}")
            
            await connector.close()
            logger.info(f"{connector.exchange_id} Test Passed.")
        except Exception as e:
            logger.error(f"{connector.exchange_id} Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connectors())
