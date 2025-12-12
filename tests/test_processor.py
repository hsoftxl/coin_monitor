import unittest
from src.models import StandardCandle
from src.processors.data_processor import DataProcessor

class TestDataProcessor(unittest.TestCase):
    def test_processing_base_volume(self):
        # Base volume candle (Binance style)
        c = StandardCandle(
            timestamp=1600000000000,
            open=100, high=110, low=90, close=100,
            volume=10, # 10 ETH
            taker_buy_volume=6, # 6 ETH
            taker_sell_volume=4, # 4 ETH
            volume_type='base',
            exchange_id='binance'
        )
        df = DataProcessor.process_candles([c])
        
        # Expected: Taker Buy USDT = 6 * 100 = 600
        # Expected: Taker Sell USDT = 4 * 100 = 400
        self.assertEqual(df.iloc[0]['taker_buy_usdt'], 600.0)
        self.assertEqual(df.iloc[0]['taker_sell_usdt'], 400.0)
        self.assertEqual(df.iloc[0]['net_flow_usdt'], 200.0)

    def test_processing_quote_volume(self):
        # Quote volume candle (OKX style)
        c = StandardCandle(
            timestamp=1600000000000,
            open=100, high=110, low=90, close=100,
            volume=10, 
            taker_buy_volume=500.0, # 500 USDT
            taker_sell_volume=300.0, 
            volume_type='quote',
            exchange_id='okx'
        )
        df = DataProcessor.process_candles([c])
        
        self.assertEqual(df.iloc[0]['taker_buy_usdt'], 500.0)
        self.assertEqual(df.iloc[0]['taker_sell_usdt'], 300.0)

if __name__ == '__main__':
    unittest.main()
