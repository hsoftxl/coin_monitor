"""
现货-合约联动分析器
分析现货和合约市场的价格联动关系，识别真实资金流向
"""

import pandas as pd
from typing import Dict, Optional, Tuple
from src.config import Config
from src.utils.logger import logger


class SpotFuturesAnalyzer:
    """
    Analyzes the correlation between spot and futures markets.
    
    Signals:
    - HIGH: Futures leading (strong leverage inflow)
    - MEDIUM: Spot and futures moving together
    - LOW/WARNING: Divergence (potential hedge activity)
    """
    
    def __init__(self):
        self.divergence_threshold = Config.SF_DIVERGENCE_THRESHOLD
        self.correlation_threshold = Config.SF_CORRELATION_THRESHOLD
    
    def analyze_correlation(
        self,
        spot_df: Optional[pd.DataFrame],
        futures_df: Optional[pd.DataFrame],
        symbol: str
    ) -> Optional[Dict]:
        """
        Analyze spot-futures correlation.
        
        Args:
            spot_df: Spot market 1m candles
            futures_df: Futures market 1m candles
            symbol: Trading symbol
            
        Returns:
            Dictionary with correlation analysis or None if data insufficient
        """
        # Check if both datasets are available
        if spot_df is None or futures_df is None:
            return None
        
        if spot_df.empty or futures_df.empty:
            return None
        
        if len(spot_df) < 2 or len(futures_df) < 2:
            return None
        
        try:
            # Get latest candle price change
            spot_current = spot_df.iloc[-1]
            spot_prev = spot_df.iloc[-2]
            
            futures_current = futures_df.iloc[-1]
            futures_prev = futures_df.iloc[-2]
            
            # Calculate percentage change
            spot_open = spot_prev['close']
            spot_close = spot_current['close']
            
            futures_open = futures_prev['close']
            futures_close = futures_current['close']
            
            if spot_open <= 0 or futures_open <= 0:
                return None
            
            spot_change_pct = ((spot_close - spot_open) / spot_open) * 100
            futures_change_pct = ((futures_close - futures_open) / futures_open) * 100
            
            # Calculate divergence
            divergence = futures_change_pct - spot_change_pct
            
            # Determine strength
            strength = self._determine_strength(spot_change_pct, futures_change_pct, divergence)
            
            return {
                'spot_change': spot_change_pct,
                'futures_change': futures_change_pct,
                'divergence': divergence,
                'strength': strength,
                'spot_price': spot_close,
                'futures_price': futures_close
            }
            
        except Exception as e:
            logger.debug(f"[{symbol}] Spot-Futures分析失败: {e}")
            return None
    
    def _determine_strength(
        self,
        spot_change: float,
        futures_change: float,
        divergence: float
    ) -> str:
        """
        Determine the correlation strength level.
        
        Args:
            spot_change: Spot price change %
            futures_change: Futures price change %
            divergence: Futures - Spot change
            
        Returns:
            'HIGH', 'MEDIUM', or 'LOW'
        """
        # Case 1: Futures leading strongly (HIGH strength)
        # Futures rise significantly more than spot
        if divergence >= self.divergence_threshold and futures_change > 0:
            return 'HIGH'
        
        # Case 2: Moving together (MEDIUM strength)
        # Both moving in same direction with similar magnitude
        if abs(divergence) <= self.correlation_threshold:
            if spot_change > 0 and futures_change > 0:
                return 'MEDIUM'
        
        # Case 3: Divergence or weak correlation (LOW strength)
        # Futures up but spot down, or significant difference
        if spot_change < -0.2 and futures_change > 0.5:
            # Potential hedge activity
            return 'LOW'
        
        # Case 4: Spot leading (MEDIUM-LOW)
        # This is less bullish than futures leading
        if divergence < -self.divergence_threshold and spot_change > 0:
            return 'MEDIUM'
        
        # Default: unclear correlation
        return 'LOW'
    
    def get_correlation_message(self, analysis: Optional[Dict]) -> str:
        """
        Generate human-readable correlation message.
        
        Args:
            analysis: Correlation analysis result
            
        Returns:
            Formatted message string
        """
        if not analysis:
            return ""
        
        spot_chg = analysis['spot_change']
        futures_chg = analysis['futures_change']
        strength = analysis['strength']
        
        if strength == 'HIGH':
            return f"🔥合约强势领涨 (现货+{spot_chg:.2f}% 合约+{futures_chg:.2f}%)"
        elif strength == 'MEDIUM':
            return f"同步上涨 (现货+{spot_chg:.2f}% 合约+{futures_chg:.2f}%)"
        elif strength == 'LOW':
            if spot_chg < 0 and futures_chg > 0:
                return f"⚠️背离 (现货{spot_chg:.2f}% 合约+{futures_chg:.2f}%)"
            else:
                return f"弱联动 (现货+{spot_chg:.2f}% 合约+{futures_chg:.2f}%)"
        
        return ""
