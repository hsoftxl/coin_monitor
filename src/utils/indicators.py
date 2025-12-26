"""
技术指标计算工具类
提供ATR、MA等常用技术指标的计算
"""

import pandas as pd
import numpy as np
from typing import Optional


def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """
    计算平均真实波幅 (Average True Range)
    
    Args:
        df: OHLC数据框，必须包含 'high', 'low', 'close' 列
        period: ATR计算周期，默认14
        
    Returns:
        当前ATR值，如果数据不足返回None
    """
    if df is None or len(df) < period + 1:
        return None
    
    try:
        # 计算True Range
        # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # 前一日收盘价
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]  # 第一个值使用自身
        
        # 三种范围
        tr1 = high - low
        tr2 = np.abs(high - prev_close)
        tr3 = np.abs(low - prev_close)
        
        # True Range = 三者最大值
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # ATR = TR的移动平均
        # 使用EMA（指数移动平均）
        atr_series = pd.Series(tr).ewm(span=period, adjust=False).mean()
        
        return float(atr_series.iloc[-1])
        
    except Exception as e:
        return None


def calculate_atr_percentage(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """
    计算ATR百分比 (ATR / 当前价格 * 100)
    用于波动率分级
    
    Args:
        df: OHLC数据框
        period: ATR计算周期
        
    Returns:
        ATR百分比，如果数据不足返回None
    """
    atr = calculate_atr(df, period)
    if atr is None or df is None or len(df) == 0:
        return None
    
    try:
        current_price = df['close'].iloc[-1]
        if current_price <= 0:
            return None
        
        return (atr / current_price) * 100
        
    except Exception:
        return None


def calculate_ma(df: pd.DataFrame, period: int = 20, column: str = 'close') -> Optional[float]:
    """
    计算简单移动平均线 (Simple Moving Average)
    
    Args:
        df: 数据框
        period: MA周期
        column: 计算MA的列名，默认'close'
        
    Returns:
        当前MA值，如果数据不足返回None
    """
    if df is None or len(df) < period or column not in df.columns:
        return None
    
    try:
        ma = df[column].rolling(window=period).mean().iloc[-1]
        return float(ma)
    except Exception:
        return None


def calculate_ema(df: pd.DataFrame, period: int = 20, column: str = 'close') -> Optional[float]:
    """
    计算指数移动平均线 (Exponential Moving Average)
    
    Args:
        df: 数据框
        period: EMA周期
        column: 计算EMA的列名，默认'close'
        
    Returns:
        当前EMA值，如果数据不足返回None
    """
    if df is None or len(df) < period or column not in df.columns:
        return None
    
    try:
        ema = df[column].ewm(span=period, adjust=False).mean().iloc[-1]
        return float(ema)
    except Exception:
        return None


def is_trend_up(df: pd.DataFrame, lookback: int = 3, column: str = 'close') -> bool:
    """
    判断是否处于上升趋势
    当前价格 > 过去N根K线的平均价格
    
    Args:
        df: 数据框
        lookback: 回溯K线数量
        column: 价格列名
        
    Returns:
        True表示上升趋势，False表示下降或震荡
    """
    if df is None or len(df) < lookback + 1 or column not in df.columns:
        return False
    
    try:
        current_price = df[column].iloc[-1]
        avg_price = df[column].iloc[-(lookback+1):-1].mean()
        
        return current_price > avg_price
        
    except Exception:
        return False


def get_volatility_level(atr_pct: Optional[float], 
                         low_threshold: float = 2.0,
                         high_threshold: float = 5.0) -> str:
    """
    根据ATR百分比判断波动率等级
    
    Args:
        atr_pct: ATR百分比
        low_threshold: 低波动阈值
        high_threshold: 高波动阈值
        
    Returns:
        'LOW', 'NORMAL', 或 'HIGH'
    """
    if atr_pct is None:
        return 'NORMAL'
    
    if atr_pct < low_threshold:
        return 'LOW'
    elif atr_pct >= high_threshold:
        return 'HIGH'
    else:
        return 'NORMAL'
