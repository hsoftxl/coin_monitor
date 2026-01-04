"""
市场环境判断模块
基于 BTC 价格走势判断当前市场环境（牛/熊/震荡）
"""

import pandas as pd
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
    """
    
    def analyze(self, btc_df: pd.DataFrame) -> Dict[str, str]:
        """
        分析市场环境
        
        Args:
            btc_df: BTC/USDT K线数据 (建议 1h 或 4h)
            
        Returns:
            {
                'regime': 'BULL' | 'BEAR' | 'NEUTRAL',
                'desc': 描述文本
            }
        """
        if btc_df is None or btc_df.empty or len(btc_df) < 65:
            return {'regime': 'NEUTRAL', 'desc': '数据不足，默认为震荡'}
            
        try:
            current_price = btc_df['close'].iloc[-1]
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
                
            return {
                'regime': regime,
                'desc': desc
            }
            
        except Exception as e:
            logger.error(f"市场环境分析失败: {e}")
            return {'regime': 'NEUTRAL', 'desc': f'分析错误: {e}'}
