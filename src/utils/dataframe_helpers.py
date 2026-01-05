"""
DataFrame 辅助函数
提供优化的 DataFrame 访问方法，减少重复的 .iloc[-1] 调用
"""

import pandas as pd
from typing import Tuple, Optional, List, Any


def get_latest_values(df: pd.DataFrame, n: int = 2) -> Tuple[pd.Series, ...]:
    """
    获取 DataFrame 的最后 n 行数据，避免重复调用 .iloc[-1]
    
    Args:
        df: 输入的 DataFrame
        n: 需要获取的行数，默认2行（最后一行和倒数第二行）
        
    Returns:
        元组，包含最后 n 行的 Series 对象
        如果数据不足，返回 None 填充
        
    Example:
        >>> current, prev = get_latest_values(df, n=2)
        >>> current_price = current['close']
        >>> prev_price = prev['close']
    """
    if df is None or df.empty or len(df) < n:
        # 返回 None 填充的元组
        return tuple([None] * n)
    
    tail_data = df.tail(n)
    # Return in reverse order: latest first (iloc[-1] equivalent), then previous
    return tuple(tail_data.iloc[-(i+1)] for i in range(len(tail_data)))


def get_latest_value(df: pd.DataFrame, column: str, default: Any = None) -> Any:
    """
    获取 DataFrame 最后一行的指定列值
    
    Args:
        df: 输入的 DataFrame
        column: 列名
        default: 如果数据不足时的默认值
        
    Returns:
        最后一行的指定列值
    """
    if df is None or df.empty or column not in df.columns:
        return default
    
    try:
        return df[column].iloc[-1]
    except (IndexError, KeyError):
        return default


def get_latest_n_values(df: pd.DataFrame, column: str, n: int = 2) -> List[Any]:
    """
    获取 DataFrame 最后 n 行的指定列值列表
    
    Args:
        df: 输入的 DataFrame
        column: 列名
        n: 需要获取的行数
        
    Returns:
        最后 n 行的列值列表
    """
    if df is None or df.empty or column not in df.columns:
        return []
    
    try:
        return df[column].tail(n).tolist()
    except (IndexError, KeyError):
        return []
