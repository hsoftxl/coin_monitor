"""
Pytest configuration and fixtures
"""

import pytest
import pandas as pd
from typing import Dict, Any
from src.core.context import AnalysisContext
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.early_pump import EarlyPumpAnalyzer
from src.analyzers.spot_futures_analyzer import SpotFuturesAnalyzer
from src.analyzers.accumulation import AccumulationAnalyzer
from src.strategies.entry_exit import EntryExitStrategy


@pytest.fixture
def sample_candle_data():
    """Sample candle data for testing"""
    return pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='1min'),
        'open': [100.0] * 100,
        'high': [101.0] * 100,
        'low': [99.0] * 100,
        'close': [100.5] * 100,
        'volume': [1000.0] * 100,
        'taker_buy_usdt': [600.0] * 100,
        'taker_sell_usdt': [400.0] * 100,
        'net_flow_usdt': [200.0] * 100
    }).set_index('timestamp')


@pytest.fixture
def sample_platform_metrics():
    """Sample platform metrics for testing"""
    return {
        'binance': {
            'cumulative_net_flow': 20000000.0,
            'buy_sell_ratio': 1.5,
            'current_price': 100.0,
            'support_low': 95.0,
            'resistance_high': 105.0,
            'atr': 2.0
        },
        'okx': {
            'cumulative_net_flow': 15000000.0,
            'buy_sell_ratio': 1.3,
            'current_price': 100.0,
            'support_low': 95.0,
            'resistance_high': 105.0,
            'atr': 2.0
        },
        'bybit': {
            'cumulative_net_flow': 10000000.0,
            'buy_sell_ratio': 1.2,
            'current_price': 100.0,
            'support_low': 95.0,
            'resistance_high': 105.0,
            'atr': 2.0
        },
        'coinbase': {
            'cumulative_net_flow': 5000000.0,
            'buy_sell_ratio': 1.1,
            'current_price': 100.0,
            'support_low': 95.0,
            'resistance_high': 105.0,
            'atr': 2.0
        }
    }


@pytest.fixture
def mock_analysis_context(mocker):
    """Mock AnalysisContext for testing"""
    connectors = {}
    
    taker_analyzer = TakerFlowAnalyzer(window=50)
    multi_analyzer = MultiPlatformAnalyzer()
    early_pump_analyzer = EarlyPumpAnalyzer()
    sf_analyzer = SpotFuturesAnalyzer()
    accumulation_analyzer = AccumulationAnalyzer()
    strategy = EntryExitStrategy()
    
    ctx = AnalysisContext(
        connectors=connectors,
        taker_analyzer=taker_analyzer,
        multi_analyzer=multi_analyzer,
        early_pump_analyzer=early_pump_analyzer,
        sf_analyzer=sf_analyzer,
        accumulation_analyzer=accumulation_analyzer,
        strategy=strategy
    )
    
    return ctx