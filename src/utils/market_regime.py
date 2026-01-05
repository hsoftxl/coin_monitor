"""
市场环境判断模块
基于 BTC 价格走势判断当前市场环境（牛/熊/震荡）
支持缓存机制，避免频繁获取数据
"""

import pandas as pd
import time
from typing import Optional, Dict
from src.utils.indicators import calculate_ma
from src.utils.logger import logger

class MarketRegimeDetector:
    """
    市场环境检测器
    
    逻辑:
    1. 获取 BTC 日线/4H 数据
    2. 判断均线排列 (MA20 vs MA60)
    3. 判断价格位置 (Price vs MA120)
    
    返回状态:
    - BULL: 牛市 (适合做多)
    - BEAR: 熊市 (适合做空)
    - NEUTRAL: 震荡 (谨慎操作)
    
    支持缓存机制，默认缓存5分钟
    """
    
    def __init__(self, cache_ttl: int = 300):
        """
        初始化市场环境检测器
        
        Args:
            cache_ttl: 缓存有效期（秒），默认300秒（5分钟）
        """
        self.cache_ttl = cache_ttl
        self._cache: Optional[Dict[str, any]] = None
        self._cache_timestamp: float = 0.0
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效
        
        Returns:
            True 如果缓存有效，False 如果缓存过期或不存在
        """
        if self._cache is None:
            return False
        current_time = time.time()
        return (current_time - self._cache_timestamp) < self.cache_ttl
    
    def get_cached_result(self) -> Optional[Dict[str, str]]:
        """
        获取缓存的结果（如果有效）
        
        Returns:
            缓存的结果，如果缓存无效则返回 None
        """
        if self.is_cache_valid():
            return self._cache
        return None
    
    def analyze(self, btc_df: pd.DataFrame, force_refresh: bool = False) -> Dict[str, str]:
        """
        分析市场环境
        
        Args:
            btc_df: BTC/USDT K线数据 (建议 1h 或 4h)
            force_refresh: 强制刷新缓存
            
        Returns:
            {
                'regime': 'BULL' | 'BEAR' | 'NEUTRAL',
                'desc': 描述文本
            }
        """
        # 检查缓存
        current_time = time.time()
        if not force_refresh and self._cache is not None:
            if current_time - self._cache_timestamp < self.cache_ttl:
                logger.debug(f"使用缓存的市场环境数据 (缓存剩余 {int(self.cache_ttl - (current_time - self._cache_timestamp))}秒)")
                return self._cache
        
        if btc_df is None or btc_df.empty or len(btc_df) < 65:
            result = {'regime': 'NEUTRAL', 'desc': '数据不足，默认为震荡'}
            self._update_cache(result)
            return result
            
        try:
            # Optimized DataFrame access
            from src.utils.dataframe_helpers import get_latest_value
            current_price = get_latest_value(btc_df, 'close', 0.0)
            ma20 = calculate_ma(btc_df, 20)
            ma60 = calculate_ma(btc_df, 60)
            
            if not ma20 or not ma60:
                return {'regime': 'NEUTRAL', 'desc': '指标计算失败'}
            
            # 判定逻辑
            regime = 'NEUTRAL'
            desc = "震荡整理"
            
            # 牛市判定: 价格 > MA20 > MA60
            if current_price > ma20 and ma20 > ma60:
                regime = 'BULL'
                desc = "多头趋势 (Price > MA20 > MA60)"
                
            # 熊市判定: 价格 < MA20 < MA60
            elif current_price < ma20 and ma20 < ma60:
                regime = 'BEAR'
                desc = "空头趋势 (Price < MA20 < MA60)"
            
            # 辅助判定: 价格与 MA60 关系
            elif current_price > ma60:
                regime = 'NEUTRAL_BULL' # 偏多震荡
                desc = "偏多震荡 (Price > MA60)"
            elif current_price < ma60:
                regime = 'NEUTRAL_BEAR' # 偏空震荡
                desc = "偏空震荡 (Price < MA60)"
                
            result = {
                'regime': regime,
                'desc': desc
            }
            self._update_cache(result)
            return result
            
        except Exception as e:
            logger.error(f"市场环境分析失败: {e}")
            result = {'regime': 'NEUTRAL', 'desc': f'分析错误: {e}'}
            self._update_cache(result)
            return result
    
    def _update_cache(self, result: Dict[str, str]):
        """
        更新缓存
        
        Args:
            result: 分析结果
        """
        self._cache = result
        self._cache_timestamp = time.time()
    
    def clear_cache(self):
        """清除缓存"""
        self._cache = None
        self._cache_timestamp = 0.0
