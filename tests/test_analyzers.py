"""
Tests for analyzer modules
"""

import pytest
import pandas as pd
import numpy as np
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.accumulation import AccumulationAnalyzer
from src.utils.indicators import (
    calculate_obv,
    is_obv_rising,
    calculate_cmf,
    calculate_price_position,
    calculate_volume_profile_poc,
    calculate_buying_pressure
)


class TestTakerFlowAnalyzer:

    def test_analyze_empty_dataframe(self):
        analyzer = TakerFlowAnalyzer(window=50)
        df = pd.DataFrame()
        result = analyzer.analyze(df)
        assert isinstance(result, dict)
        assert 'net_flow' in result or 'cumulative_net_flow' in result
        assert 'trend' in result or 'buy_sell_ratio' in result
    
    def test_analyze_with_data(self, sample_candle_data):
        analyzer = TakerFlowAnalyzer(window=50)
        result = analyzer.analyze(sample_candle_data)
        assert 'cumulative_net_flow' in result
        assert 'buy_sell_ratio' in result
        assert 'current_price' in result
        assert result['cumulative_net_flow'] > 0


class TestMultiPlatformAnalyzer:

    def test_analyze_signals_bullish(self, sample_platform_metrics):
        analyzer = MultiPlatformAnalyzer()
        signals = analyzer.analyze_signals(sample_platform_metrics, symbol='BTC/USDT')
        assert isinstance(signals, list)
    
    def test_analyze_signals_empty(self):
        analyzer = MultiPlatformAnalyzer()
        signals = analyzer.analyze_signals({}, symbol='BTC/USDT')
        assert signals == []


class TestIndicators:

    def test_calculate_obv(self):
        df = pd.DataFrame({
            'close': [10.0, 10.5, 10.3, 10.8, 11.0],
            'volume': [100, 200, 150, 300, 250]
        })
        obv = calculate_obv(df)
        assert obv is not None
        assert len(obv) == 5

    def test_calculate_cmf(self):
        np.random.seed(42)
        n = 50
        price = 100 + np.cumsum(np.random.randn(n) * 0.5)
        df = pd.DataFrame({
            'open': price - 0.2,
            'high': price + 0.5,
            'low': price - 0.5,
            'close': price + 0.1,
            'volume': np.random.randint(500, 2000, n)
        })
        cmf = calculate_cmf(df, period=20)
        assert cmf is not None
        assert isinstance(cmf, float)
        assert -1.0 <= cmf <= 1.0

    def test_calculate_price_position(self):
        df = pd.DataFrame({
            'open': [100]*80,
            'high': [105]*80,
            'low': [95]*80,
            'close': [98]*80,
            'volume': [1000]*80
        })
        pos = calculate_price_position(df, lookback=60)
        assert pos is not None
        assert 0.0 <= pos <= 1.0

    def test_calculate_volume_profile_poc(self):
        df = pd.DataFrame({
            'close': [100.0]*40 + [102.0]*40,
            'volume': [1000]*80
        })
        poc, dist = calculate_volume_profile_poc(df, bins=10, lookback=60)
        assert poc is not None

    def test_calculate_buying_pressure(self):
        df = pd.DataFrame({
            'open': [100],
            'high': [105],
            'low': [95],
            'close': [103],
            'volume': [1000]
        })
        bp = calculate_buying_pressure(df)
        assert bp is not None
        assert bp > 0.5


class TestAccumulationAnalyzer:

    def test_analyze_insufficient_data(self):
        analyzer = AccumulationAnalyzer()
        df = pd.DataFrame({
            'open': [100], 'high': [101], 'low': [99], 'close': [100],
            'volume': [1000]
        })
        result = analyzer.analyze(df, 'TEST/USDT')
        assert result is None

    def test_analyze_low_volume(self):
        analyzer = AccumulationAnalyzer()
        n = 80
        df = pd.DataFrame({
            'open': [100.0]*n, 'high': [101.0]*n, 'low': [99.0]*n,
            'close': [100.0]*n, 'volume': [100.0]*n
        })
        df.loc[df.index[-1], 'volume'] = 200.0
        result = analyzer.analyze(df, 'TEST/USDT')
        assert result is None