"""
技术指标计算工具类
提供ATR、MA、OBV、CMF、Volume Profile等常用技术指标的计算
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple


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


def calculate_obv(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    计算 On-Balance Volume (OBV)
    
    OBV根据收盘价涨跌累加/减去成交量，反映资金流入流出趋势。
    
    Args:
        df: OHLC数据框，必须包含 'close' 和 'volume' 列
        
    Returns:
        OBV Series，如果数据不足返回 None
    """
    if df is None or len(df) < 2:
        return None
    
    close = df['close'].values
    volume = df['volume'].values
    
    obv = np.zeros(len(df))
    obv[0] = volume[0]
    
    for i in range(1, len(df)):
        if close[i] > close[i-1]:
            obv[i] = obv[i-1] + volume[i]
        elif close[i] < close[i-1]:
            obv[i] = obv[i-1] - volume[i]
        else:
            obv[i] = obv[i-1]
    
    return pd.Series(obv, index=df.index)


def is_obv_rising(df: pd.DataFrame, bars: int = 3) -> bool:
    """
    判断最近 N 根 K 线的 OBV 是否持续上升（资金持续净流入）
    
    Args:
        df: OHLC数据框
        bars: 检查的K线数量
        
    Returns:
        True 如果 OBV 持续上升
    """
    obv = calculate_obv(df)
    if obv is None or len(obv) < bars + 1:
        return False
    
    recent = obv.iloc[-(bars + 1):].values
    for j in range(1, len(recent)):
        if recent[j] <= recent[j-1]:
            return False
    
    return True


def calculate_cmf(df: pd.DataFrame, period: int = 20) -> Optional[float]:
    """
    计算 Chaikin Money Flow (CMF)
    
    CMF = SUM(AD * Volume, period) / SUM(Volume, period)
    其中 AD = ((close - low) - (high - close)) / (high - low)
    CMF > 0 表示资金净流入，< 0 表示净流出。
    
    Args:
        df: OHLC数据框，必须包含 'high', 'low', 'close', 'volume' 列
        period: 计算周期，默认20
        
    Returns:
        当前CMF值，如果数据不足返回 None
    """
    if df is None or len(df) < period + 1:
        return None
    
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    volume = df['volume'].values
    
    hl_range = high - low
    hl_range[hl_range == 0] = np.nan
    
    money_flow_multiplier = np.where(
        ~np.isnan(hl_range),
        ((close - low) - (high - close)) / hl_range,
        0.0
    )
    money_flow_multiplier = np.nan_to_num(money_flow_multiplier, nan=0.0)
    
    money_flow_volume = money_flow_multiplier * volume
    
    mfv_sum = pd.Series(money_flow_volume).rolling(window=period).sum()
    vol_sum = pd.Series(volume).rolling(window=period).sum()
    
    cmf_series = np.where(vol_sum > 0, mfv_sum / vol_sum, 0.0)
    
    return float(cmf_series[-1])


def calculate_price_position(df: pd.DataFrame, lookback: int = 60) -> Optional[float]:
    """
    计算价格在近期范围内的位置比例
    
    ratio = (close - rolling_low) / (rolling_high - rolling_low)
    ratio < 0.35 表示处于低位/积累区
    
    Args:
        df: OHLC数据框，必须包含 'close', 'high', 'low' 列
        lookback: 回溯K线数量
        
    Returns:
        价格位置比例，如果数据不足返回 None
    """
    if df is None or len(df) < lookback:
        return None
    
    recent = df.iloc[-lookback:]
    close = recent['close'].iloc[-1]
    recent_high = recent['high'].max()
    recent_low = recent['low'].min()
    
    price_range = recent_high - recent_low
    if price_range <= 0:
        return 0.5
    
    return (close - recent_low) / price_range


def calculate_volume_profile_poc(df: pd.DataFrame, bins: int = 40, lookback: int = 80) -> Tuple[Optional[float], Optional[float]]:
    """
    计算简化版 Volume Profile 的 POC (Point of Control)
    
    将最近 lookback 根K线的收盘价分成 bins 个价格桶，
    用成交量加权，找到成交量最大的价格区间（POC）。
    
    Args:
        df: OHLC数据框，必须包含 'close' 和 'volume' 列
        bins: 价格桶数量
        lookback: 回溯K线数量
        
    Returns:
        (POC价格, 当前价格到POC的距离百分比)，数据不足返回 (None, None)
    """
    if df is None or len(df) < lookback:
        return None, None
    
    recent = df.iloc[-lookback:]
    closes = recent['close'].values
    volumes = recent['volume'].values
    
    price_min = closes.min()
    price_max = closes.max()
    
    if price_max <= price_min:
        return None, None
    
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    volume_profile = np.zeros(bins)
    
    for i in range(len(closes)):
        idx = np.digitize(closes[i], bin_edges) - 1
        if 0 <= idx < bins:
            volume_profile[idx] += volumes[i]
    
    poc_idx = np.argmax(volume_profile)
    poc_price = (bin_edges[poc_idx] + bin_edges[min(poc_idx + 1, bins)]) / 2
    
    current_close = closes[-1]
    poc_distance_pct = abs(current_close - poc_price) / poc_price * 100 if poc_price > 0 else None
    
    return poc_price, poc_distance_pct


def is_close_to_poc(poc_distance_pct: Optional[float], threshold: float = 2.0) -> bool:
    """
    判断当前价格是否接近 POC 支撑区
    
    Args:
        poc_distance_pct: 当前价格到POC的距离百分比
        threshold: 距离阈值（百分比）
        
    Returns:
        True 如果价格在 POC 附近
    """
    if poc_distance_pct is None:
        return False
    return poc_distance_pct <= threshold


def calculate_buying_pressure(df: pd.DataFrame) -> Optional[float]:
    """
    计算单根K线的买方压力比例
    
    (close - low) / (high - low)
    > 0.5 表示收盘在上半部分，买盘积极
    <= 0.5 表示收盘在下半部分，卖盘压制
    
    Args:
        df: OHLC数据框
        
    Returns:
        买方压力比例，数据不足返回 None
    """
    if df is None or len(df) < 1:
        return None
    
    latest = df.iloc[-1]
    hl_range = latest['high'] - latest['low']
    
    if hl_range <= 0:
        return 0.5
    
    return (latest['close'] - latest['low']) / hl_range
