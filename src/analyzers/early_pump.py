
import pandas as pd
import time
from typing import Dict
from src.config import Config
from src.utils.logger import logger

class EarlyPumpAnalyzer:
    """
    Analyzes the 'initial stage' of a pump using 1-minute data specifically.
    Focuses on:
    1. Rapid price acceleration (> 1% in 1 min)
    2. Taker Buy dominance (> 60%)
    3. Volume explosion (> 5x 1h average)
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_sec = Config.EARLY_PUMP_COOLDOWN * 60
        self.min_change = Config.EARLY_PUMP_MIN_CHANGE
        self.vol_factor = Config.EARLY_PUMP_VOL_FACTOR
        self.buy_ratio_threshold = Config.EARLY_PUMP_BUY_RATIO
        
        # Lookback for volume average (1 hour)
        self.history_window = 60

    def analyze(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Detects early pump signals.
        """
        if df.empty or len(df) < (self.history_window + 2):
            return None

        # Check cooldown
        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        # Get latest closed candle
        # Assuming df is 1m candles.
        current = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Price Check: Close > Open significantly
        open_price = current['open']
        close_price = current['close']
        
        if open_price <= 0:
            return None
            
        pct_change = ((close_price - open_price) / open_price) * 100
        
        if pct_change < self.min_change:
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
        # Taker Buy Volume / Total Volume
        taker_buy = current.get('taker_buy_volume', 0)
        total_vol = current['volume']
        
        if total_vol > 0:
            buy_ratio = taker_buy / total_vol
        else:
            buy_ratio = 0.0
            
        if buy_ratio < self.buy_ratio_threshold:
            return None
            
        # Triggered!
        self.cooldowns[symbol] = now
        
        return {
            'type': 'EARLY_PUMP',
            'grade': 'A+', # Urgent
            'desc': f"🚀 主力拉盘启动: 1m涨幅+ {pct_change:.2f}%, 量能 {vol_ratio:.1f}x, 主动买入 {buy_ratio*100:.0f}%",
            'pct_change': pct_change,
            'vol_ratio': vol_ratio,
            'buy_ratio': buy_ratio,
            'price': close_price
        }
