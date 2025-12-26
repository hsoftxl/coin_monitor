
import pandas as pd
import time
from typing import Dict, Optional, Tuple
from src.config import Config
from src.utils.logger import logger
from src.utils.indicators import (
    calculate_atr_percentage, 
    calculate_ma, 
    is_trend_up,
    get_volatility_level
)

class EarlyPumpAnalyzer:
    """
    Analyzes the 'initial stage' of a pump using 1-minute data specifically.
    
    Enhanced with:
    1. Multi-timeframe confirmation (5m trend + 1h MA)
    2. Adaptive volatility threshold
    3. Spot-Futures correlation support
    
    Focuses on:
    1. Rapid price acceleration (adaptive % based on volatility)
    2. Taker Buy dominance (> 60%)
    3. Volume explosion (> 5x 1h average)
    4. Multi-timeframe trend confirmation
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_sec = Config.EARLY_PUMP_COOLDOWN * 60
        self.min_change = Config.EARLY_PUMP_MIN_CHANGE
        self.vol_factor = Config.EARLY_PUMP_VOL_FACTOR
        self.buy_ratio_threshold = Config.EARLY_PUMP_BUY_RATIO
        
        # Multi-timeframe settings
        self.enable_mtf = Config.ENABLE_MULTI_TIMEFRAME
        self.mtf_5m_bars = Config.MTF_5M_TREND_BARS
        self.mtf_1h_ma_period = Config.MTF_1H_MA_PERIOD
        
        # Adaptive threshold settings
        self.enable_adaptive = Config.ENABLE_ADAPTIVE_THRESHOLD
        self.atr_period = Config.ATR_PERIOD
        
        # Lookback for volume average (1 hour)
        self.history_window = 60

    def _get_adaptive_threshold(self, df: pd.DataFrame, current_price: float) -> Tuple[float, str]:
        """
        Get adaptive threshold based on volatility.
        
        Returns:
            (threshold, volatility_level)
        """
        if not self.enable_adaptive:
            return self.min_change, 'NORMAL'
        
        # Calculate ATR percentage
        atr_pct = calculate_atr_percentage(df, self.atr_period)
        
        if atr_pct is None:
            return self.min_change, 'NORMAL'
        
        # Determine volatility level
        vol_level = get_volatility_level(
            atr_pct,
            Config.VOLATILITY_LOW_THRESHOLD,
            Config.VOLATILITY_HIGH_THRESHOLD
        )
        
        # Select threshold based on volatility
        if vol_level == 'LOW':
            threshold = Config.PUMP_THRESHOLD_LOW_VOL
        elif vol_level == 'HIGH':
            threshold = Config.PUMP_THRESHOLD_HIGH_VOL
        else:
            threshold = Config.PUMP_THRESHOLD_NORMAL_VOL
        
        return threshold, vol_level

    def _check_multi_timeframe(
        self, 
        df_5m: Optional[pd.DataFrame], 
        df_1h: Optional[pd.DataFrame],
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Check multi-timeframe confirmation.
        
        Returns:
            (is_confirmed, status_message)
        """
        if not self.enable_mtf:
            return True, ""
        
        if df_5m is None or df_1h is None:
            # If MTF data not available, skip this check (backward compatible)
            return True, "MTF数据不足"
        
        # Check 5m trend
        trend_5m_ok = is_trend_up(df_5m, self.mtf_5m_bars)
        
        # Check 1h MA20
        ma_1h = calculate_ma(df_1h, self.mtf_1h_ma_period)
        ma_1h_ok = ma_1h is not None and current_price > ma_1h
        
        # Both must be true
        if trend_5m_ok and ma_1h_ok:
            return True, "✓5m趋势+1hMA"
        elif not trend_5m_ok:
            return False, "✗5m趋势下行"
        else:
            return False, "✗低于1hMA20"

    def analyze(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        df_5m: Optional[pd.DataFrame] = None,
        df_1h: Optional[pd.DataFrame] = None,
        sf_strength: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Detects early pump signals with enhanced multi-timeframe and volatility analysis.
        
        Args:
            df: 1m candle data
            symbol: Trading symbol
            df_5m: Optional 5m candle data for trend confirmation
            df_1h: Optional 1h candle data for MA confirmation
            sf_strength: Optional spot-futures correlation strength ('HIGH', 'MEDIUM', 'LOW')
        """
        if df.empty or len(df) < (self.history_window + 2):
            return None

        # Check cooldown
        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        # Get latest closed candle
        current = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Price Check: Close > Open significantly
        open_price = current['open']
        close_price = current['close']
        
        if open_price <= 0:
            return None
            
        pct_change = ((close_price - open_price) / open_price) * 100
        
        # Get adaptive threshold based on volatility
        threshold, vol_level = self._get_adaptive_threshold(df, close_price)
        
        if pct_change < threshold:
            return None
            
        # 2. Volume Check: Current Volume vs Prev 60m Average
        hist_df = df.iloc[-(self.history_window+1):-1]
        avg_vol = hist_df['volume'].mean()
        
        if avg_vol <= 0:
            avg_vol = 1.0 # Protect division
            
        vol_ratio = current['volume'] / avg_vol
        
        if vol_ratio < self.vol_factor:
            return None
            
        # 3. Taker Buy Ratio
        taker_buy = current.get('taker_buy_volume', 0)
        total_vol = current['volume']
        
        if total_vol > 0:
            buy_ratio = taker_buy / total_vol
        else:
            buy_ratio = 0.0
            
        if buy_ratio < self.buy_ratio_threshold:
            return None
        
        # 4. Multi-timeframe confirmation
        mtf_confirmed, mtf_msg = self._check_multi_timeframe(df_5m, df_1h, close_price)
        
        if not mtf_confirmed:
            logger.debug(f"[{symbol}] MTF未确认: {mtf_msg}")
            return None
            
        # Triggered!
        self.cooldowns[symbol] = now
        
        # Build detailed description
        vol_tag = {'LOW': '低波', 'NORMAL': '中波', 'HIGH': '高波'}.get(vol_level, '中波')
        
        desc_parts = [
            f"🚀 主力拉盘启动: 1m涨幅+ {pct_change:.2f}%",
            f"量能 {vol_ratio:.1f}x",
            f"主动买入 {buy_ratio*100:.0f}%",
            f"[{vol_tag}]"
        ]
        
        if mtf_msg:
            desc_parts.append(mtf_msg)
        
        if sf_strength:
            sf_tag = {'HIGH': '🔥合约强势', 'MEDIUM': '同步', 'LOW': '⚠️现货弱'}.get(sf_strength, '')
            if sf_tag:
                desc_parts.append(sf_tag)
        
        # Determine grade based on all factors
        grade = self._calculate_grade(pct_change, vol_ratio, buy_ratio, vol_level, mtf_confirmed, sf_strength)
        
        return {
            'type': 'EARLY_PUMP',
            'grade': grade,
            'desc': " | ".join(desc_parts),
            'pct_change': pct_change,
            'vol_ratio': vol_ratio,
            'buy_ratio': buy_ratio,
            'price': close_price,
            'volatility_level': vol_level,
            'mtf_confirmed': mtf_confirmed,
            'sf_strength': sf_strength or 'N/A'
        }

    def _calculate_grade(
        self,
        pct_change: float,
        vol_ratio: float,
        buy_ratio: float,
        vol_level: str,
        mtf_confirmed: bool,
        sf_strength: Optional[str]
    ) -> str:
        """
        Calculate signal grade based on multiple factors.
        
        Grade system:
        A+ : Exceptional (all factors strong + SF correlation HIGH)
        A  : Strong (all factors good)
        B+ : Good (most factors good)
        """
        score = 0
        
        # Price change score (0-3 points)
        if pct_change >= 2.0:
            score += 3
        elif pct_change >= 1.5:
            score += 2
        else:
            score += 1
        
        # Volume score (0-2 points)
        if vol_ratio >= 10:
            score += 2
        elif vol_ratio >= 7:
            score += 1
        
        # Buy ratio score (0-2 points)
        if buy_ratio >= 0.75:
            score += 2
        elif buy_ratio >= 0.65:
            score += 1
        
        # MTF bonus (0-2 points)
        if mtf_confirmed:
            score += 2
        
        # SF correlation bonus (0-2 points)
        if sf_strength == 'HIGH':
            score += 2
        elif sf_strength == 'MEDIUM':
            score += 1
        
        # Volatility penalty for HIGH volatility
        if vol_level == 'HIGH':
            score -= 1
        
        # Determine grade
        if score >= 10:
            return 'A+'
        elif score >= 7:
            return 'A'
        else:
            return 'B+'
