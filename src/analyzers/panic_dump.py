
import pandas as pd
import time
from typing import Dict, Optional, Tuple
from src.config import Config
from src.utils.logger import logger
from src.utils.indicators import (
    calculate_atr_percentage, 
    calculate_ma, 
    is_trend_up, # Can we check downtrend? Need is_trend_down or inverse logic
    get_volatility_level
)

class PanicDumpAnalyzer:
    """
    Analyzes 'Panic Dump' or 'Institutional Distribution' signals.
    
    Opposite of EarlyPumpAnalyzer.
    
    Focuses on:
    1. Rapid price drop (adaptive % based on volatility)
    2. Taker Sell dominance (> 60% or Buy/Sell Ratio < 0.4)
    3. Volume explosion (> 5x 1h average)
    4. Multi-timeframe trend confirmation (Downtrend)
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_sec = Config.EARLY_PUMP_COOLDOWN * 60
        # Use config for drop threshold if available, else derive or default
        # Assuming we might want a separate config, but reusing MIN_CHANGE is okay for now or use hardcoded default
        self.min_drop = getattr(Config, 'PANIC_DUMP_MIN_DROP', 1.0) 
        self.vol_factor = Config.EARLY_PUMP_VOL_FACTOR
        self.sell_ratio_threshold = getattr(Config, 'PANIC_DUMP_SELL_RATIO', 0.6)
        
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
        Returns: (threshold, volatility_level)
        """
        if not self.enable_adaptive:
            return self.min_drop, 'NORMAL'
        
        atr_pct = calculate_atr_percentage(df, self.atr_period)
        
        if atr_pct is None:
            return self.min_drop, 'NORMAL'
        
        vol_level = get_volatility_level(
            atr_pct,
            Config.VOLATILITY_LOW_THRESHOLD,
            Config.VOLATILITY_HIGH_THRESHOLD
        )
        
        # Reuse pump thresholds for drop
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
        Check multi-timeframe confirmation for DUMP.
        We want 5m downtrend and Price < 1h MA.
        """
        if not self.enable_mtf:
            return True, ""
        
        if df_5m is None or df_1h is None:
            return True, "MTF数据不足"
        
        # Check 5m trend (Down)
        # Re-use is_trend_up logic but invert? Or implement is_trend_down
        # Simple check: MA5 < MA10 or Close < MA20
        # Let's use simple logic here:
        close_5m = df_5m['close'].iloc[-1]
        ma20_5m = df_5m['close'].rolling(20).mean().iloc[-1]
        trend_5m_down = close_5m < ma20_5m
        
        # Check 1h MA20
        ma_1h = calculate_ma(df_1h, self.mtf_1h_ma_period)
        ma_1h_ok = ma_1h is not None and current_price < ma_1h
        
        if trend_5m_down and ma_1h_ok:
            return True, "✓5m趋势下行+1hMA压制"
        elif not trend_5m_down:
            return False, "✗5m趋势未确认"
        else:
            return False, "✗高于1hMA20"

    def analyze(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        df_5m: Optional[pd.DataFrame] = None,
        df_1h: Optional[pd.DataFrame] = None,
        sf_strength: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Detects panic dump signals.
        """
        if df.empty or len(df) < (self.history_window + 2):
            return None

        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        current = df.iloc[-1]
        
        # 1. Price Check: Close < Open significantly
        open_price = current['open']
        close_price = current['close']
        
        if open_price <= 0: return None
            
        # Calculate drop percentage (positive value for drop)
        drop_pct = ((open_price - close_price) / open_price) * 100
        
        # Ignore pumps (close > open)
        if close_price >= open_price:
            return None
        
        threshold, vol_level = self._get_adaptive_threshold(df, close_price)
        
        if drop_pct < threshold:
            return None
            
        # 2. Volume Check
        hist_df = df.iloc[-(self.history_window+1):-1]
        avg_vol = hist_df['volume'].mean()
        if avg_vol <= 0: avg_vol = 1.0
            
        vol_ratio = current['volume'] / avg_vol
        
        if vol_ratio < self.vol_factor:
            return None
            
        # 3. Taker Sell Ratio (or low Buy Ratio)
        taker_buy = current.get('taker_buy_volume', 0)
        total_vol = current['volume']
        
        if total_vol > 0:
            buy_ratio = taker_buy / total_vol
            sell_ratio = 1.0 - buy_ratio
        else:
            sell_ratio = 0.0
            
        if sell_ratio < self.sell_ratio_threshold:
            return None
        
        # 4. MTF Confirmation
        mtf_confirmed, mtf_msg = self._check_multi_timeframe(df_5m, df_1h, close_price)
        
        if not mtf_confirmed:
            return None
            
        # Triggered!
        self.cooldowns[symbol] = now
        
        vol_tag = {'LOW': '低波', 'NORMAL': '中波', 'HIGH': '高波'}.get(vol_level, '中波')
        
        desc_parts = [
            f"📉 主力暴力出货: 1m跌幅 -{drop_pct:.2f}%",
            f"量能 {vol_ratio:.1f}x",
            f"主动卖出 {sell_ratio*100:.0f}%",
            f"[{vol_tag}]"
        ]
        
        if mtf_msg:
            desc_parts.append(mtf_msg)
            
        # Grade
        grade = 'A' # Default A for confirmed dump
        if drop_pct > 2.0 and vol_ratio > 10:
            grade = 'A+'
        
        return {
            'type': 'PANIC_DUMP',
            'grade': grade,
            'desc': " | ".join(desc_parts),
            'pct_change': -drop_pct,
            'vol_ratio': vol_ratio,
            'sell_ratio': sell_ratio,
            'price': close_price,
            'volatility_level': vol_level,
            'mtf_confirmed': mtf_confirmed
        }
