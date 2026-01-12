
import pandas as pd
import time
from typing import Dict, List
from src.config import Config
from src.utils.logger import logger

class VolumeSpikeAnalyzer:
    """
    Analyzes volume spikes based on rolling 15m windows using 1m data.
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}  # symbol -> last_alert_timestamp
        self.history_window = 60   # 5 hours (60 * 5m)
        self.spike_window = 3      # 15 minutes (3 * 5m)
        self.factor = Config.SPIKE_VOL_FACTOR
        self.min_price_change = Config.SPIKE_MIN_PRICE_CHANGE
        self.cooldown_sec = Config.SPIKE_COOLDOWN_MINUTES * 60

    def analyze(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Detects volume spikes.
        Returns a dict with details if spike detected, else None.
        """
        if df.empty or len(df) < (self.history_window + self.spike_window):
            return None

        # Check cooldown
        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        # 1. Calculate Recent 15m Volume (last 15 rows)
        current_window = df.tail(self.spike_window)
        current_vol = current_window['volume'].sum()
        
        # 2. Calculate Baseline Volume (Average of previous 15m chunks over 5 hours)
        # We take the data preceding the current window
        history_df = df.iloc[-(self.history_window + self.spike_window):-self.spike_window]
        
        # Determine average volume for a 15m period in history
        # With 5m candles, a 15m chunks is 3 rows.
        # Average volume per 15m = Average volume per candle * 3
        if len(history_df) > 0:
            avg_candle_vol = history_df['volume'].mean()
            avg_15m_vol = avg_candle_vol * 3
        else:
            avg_15m_vol = 0
        
        if avg_15m_vol <= 0:
            return None
            
        ratio = current_vol / avg_15m_vol
        
        # 3. Check Price Condition
        # Close of last candle vs Open of 15 candles ago
        freq_open = current_window['open'].iloc[0]
        current_close = current_window['close'].iloc[-1]
        
        # Price Change %
        if freq_open > 0:
            pct_change = ((current_close - freq_open) / freq_open) * 100
        else:
            pct_change = 0.0
        
        # 4. 用户要求：最近3根k线的平均成交量 > 过去10根k线平均值的1.3倍
        recent_3_avg = 0.0
        past_10_avg = 0.0
        meets_3_vs_10_condition = False
        
        if len(df) >= 13:  # 至少需要13根k线数据
            recent_3_df = df.tail(3)
            recent_3_avg = recent_3_df['volume'].mean()
            past_10_df = df.iloc[-13:-3]  # 过去10根k线（排除最近3根）
            past_10_avg = past_10_df['volume'].mean()
            meets_3_vs_10_condition = recent_3_avg > (past_10_avg * 1.3)
        
        # Trigger Conditions
        # A. Volume > Factor (3.0)
        # B. Price Rising (Close > Open)
        # C. Price Change >= Min (0.5%)
        # D. 最近3根k线成交量 > 过去10根k线平均值的1.3倍
        
        is_spike = (ratio >= self.factor) and (pct_change >= self.min_price_change) and meets_3_vs_10_condition
        
        if is_spike:
            # Update cooldown
            self.cooldowns[symbol] = now
            
            return {
                'type': 'VOLUME_SPIKE',
                'desc': f"15m成交量暴增 {ratio:.1f}x (涨幅 {pct_change:.2f}%)",
                'ratio': ratio,
                'current_vol': current_vol,
                'avg_vol': avg_15m_vol,
                'price_change': pct_change,
                'current_price': current_close,
                'grade': 'A' if ratio > 5 else 'B',
                'recent_3_avg': recent_3_avg,
                'past_10_avg': past_10_avg,
                '3_vs_10_ratio': recent_3_avg / past_10_avg
            }
            
        return None
