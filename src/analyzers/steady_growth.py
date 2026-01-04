
import pandas as pd
import numpy as np
import time
from typing import Dict, Optional, Tuple
from loguru import logger

class SteadyGrowthAnalyzer:
    """
    Analyzes 'Steady Growth' (稳步上涨) signals.
    Focuses on:
    1. MA Alignment (Price > MA20 > MA60)
    2. Low Volatility Growth (No massive pumps)
    3. Consistent Upward Slope
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_sec = 3600 # 1 hour cooldown for steady signals to avoid spam
        
        # Configuration
        self.min_ma_slope = 0.0005 # Min slope for MA20
        self.max_price_deviation = 0.05 # Max deviation from MA20 (5%)
        self.alignment_bars = 5 # Number of bars required for alignment
        self.max_candle_change = 3.0 # Max % change per candle (to filter pumps)

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        Detects steady growth.
        Args:
            df: 15m candle data (Resonance timeframe)
        """
        if df is None or df.empty or len(df) < 65:
            return None
            
        # Check cooldown
        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        # Calculate MAs
        df = df.copy()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # Get recent data
        recent = df.tail(self.alignment_bars)
        
        # 1. Check MA Alignment (Bullish) for last N bars
        # Condition: Close > MA20 > MA60
        aligned = True
        for i in range(len(recent)):
            row = recent.iloc[i]
            if not (row['close'] > row['ma20'] > row['ma60']):
                aligned = False
                break
        
        if not aligned:
            return None
            
        # 2. Check for "Steady" (No massive pumps in recent history)
        # We want "Slow & Steady", not "Pump & Dump"
        # Check if any recent candle > max_candle_change
        max_pct = recent.apply(lambda row: abs((row['close']-row['open'])/row['open']*100), axis=1).max()
        if max_pct > self.max_candle_change:
            return None
            
        # 3. Check Slope (MA20 should be rising)
        # Slope = (MA20_current - MA20_prev) / MA20_prev
        ma20_curr = recent['ma20'].iloc[-1]
        ma20_prev = recent['ma20'].iloc[0] # N bars ago
        slope = (ma20_curr - ma20_prev) / ma20_prev
        
        if slope < self.min_ma_slope:
            return None
            
        # 4. Success!
        self.cooldowns[symbol] = now
        current_price = recent['close'].iloc[-1]
        
        # Calculate Strategy Targets (Trend Following)
        # SL: Below MA60 or recent low
        ma60 = recent['ma60'].iloc[-1]
        sl = ma60 * 0.99
        risk = current_price - sl
        tp = current_price + (risk * 2.5) # Aim for 1:2.5 for trend following
        
        return {
            'type': 'STEADY_GROWTH',
            'desc': f"稳步上涨趋势确认 (MA多头排列, 斜率+{slope*100:.2f}%)",
            'price': current_price,
            'grade': 'A', # High quality trend
            'strategy': {
                'action': 'LONG',
                'entry': current_price,
                'sl': sl,
                'tp': tp,
                'risk_reward': 2.5
            }
        }
