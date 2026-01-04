
import pandas as pd
import time
from typing import Dict, Optional, Tuple, List
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
    2. Adaptive volatility threshold
    3. Spot-Futures correlation
    4. Whale Confirmation & Strategy Targets
    5. 5m/15m Resonance (5m Pump + 15m Trend UP)
    """
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_sec = Config.EARLY_PUMP_COOLDOWN * 60
        self.min_change = Config.EARLY_PUMP_MIN_CHANGE
        self.vol_factor = Config.EARLY_PUMP_VOL_FACTOR
        self.buy_ratio_threshold = Config.EARLY_PUMP_BUY_RATIO
        
        # Resonance settings
        self.enable_mtf = Config.ENABLE_MULTI_TIMEFRAME
        self.res_ma_period = 20 # 15m MA20 for trend check
        
        # Adaptive threshold settings
        self.enable_adaptive = Config.ENABLE_ADAPTIVE_THRESHOLD
        self.atr_period = Config.ATR_PERIOD
        
        # Lookback for volume average (调整为20根5m = 100分钟)
        self.history_window = 20

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

    def _check_resonance(
        self, 
        df_res: Optional[pd.DataFrame], 
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Check 15m resonance.
        Requirement: 15m Trend Bullish (Price > MA20)
        """
        if not self.enable_mtf:
            return True, ""
        
        if df_res is None or df_res.empty:
            return True, "共振数据不足"
        
        # Check 15m MA20
        ma_res = calculate_ma(df_res, self.res_ma_period)
        
        # Resonance Condition: Price > 15m MA20
        # Ideally, we also want 15m to be capable of pump (not overextended), but for now just trend check.
        if ma_res is not None and current_price > ma_res:
             return True, "✓15m趋势共振"
        else:
             return False, "✗15m趋势未确认"

    def analyze(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        df_res: Optional[pd.DataFrame] = None,
        sf_strength: Optional[str] = None,
        whales: Optional[List[Dict]] = None
    ) -> Optional[Dict]:
        """
        Detects early pump signals with 5m/15m resonance.
        
        Args:
            df: 5m candle data (Base)
            symbol: Trading symbol
            df_res: Optional 15m candle data for resonance
            sf_strength: Optional spot-futures correlation strength
            whales: Optional list of recent whale trades
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
        
        # 4. Resonance Confirmation
        mtf_confirmed, mtf_msg = self._check_resonance(df_res, close_price)
        
        if not mtf_confirmed:
            logger.debug(f"[{symbol}] 共振未确认: {mtf_msg}")
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
        
        # 5. Whale Confirmation
        whale_bonus = False
        if whales:
            # Check for recent Buy whales (last 3 minutes approx)
            # Simple check: any buy whale in the passed list?
            # Assuming 'whales' passed are relevant to current time
            buy_whales = [w for w in whales if w['side'].upper() == 'BUY']
            if buy_whales:
                whale_bonus = True
                total_whale_vol = sum(w['cost'] for w in buy_whales)
                desc_parts.append(f"🐋主力抢筹${total_whale_vol/1000:.0f}k")

        # Determine grade based on all factors
        grade = self._calculate_grade(pct_change, vol_ratio, buy_ratio, vol_level, mtf_confirmed, sf_strength, whale_bonus)
        
        # 6. Calculate Strategy Targets with Dynamic ATR-based Stop Loss
        entry_price = close_price
        
        # 动态止损：基于ATR (避免过紧止损)
        atr = calculate_atr_percentage(df, self.atr_period)
        
        if atr and atr > 0:
            # ATR * 1.5 作为止损距离，限制在 1%-3% 之间
            sl_distance_pct = max(1.0, min(3.0, atr * 1.5))
        else:
            # 降级方案：根据波动率等级设定固定止损
            sl_map = {'LOW': 1.0, 'NORMAL': 1.5, 'HIGH': 2.5}
            sl_distance_pct = sl_map.get(vol_level, 1.5)
        
        stop_loss = entry_price * (1 - sl_distance_pct / 100)
        risk = entry_price - stop_loss
        
        # 动态盈亏比：根据波动率调整
        if vol_level == 'HIGH':
            risk_reward = 2.0  # 高波降低盈亏比（快进快出）
        elif vol_level == 'LOW':
            risk_reward = 3.0  # 低波提高盈亏比（稳健持有）
        else:
            risk_reward = 2.5  # 正常波动
        
        take_profit = entry_price + (risk * risk_reward)
        
        
        strategy = {
            'action': 'LONG',
            'entry': entry_price,
            'sl': stop_loss,
            'tp': take_profit,
            'risk_reward': risk_reward,
            'sl_distance_pct': sl_distance_pct
        }

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
            'sf_strength': sf_strength or 'N/A',
            'strategy': strategy
        }

    def _calculate_grade(
        self,
        pct_change: float,
        vol_ratio: float,
        buy_ratio: float,
        vol_level: str,
        mtf_confirmed: bool,
        sf_strength: Optional[str],
        whale_bonus: bool = False
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
            
        # Whale bonus (2 points)
        if whale_bonus:
            score += 2
        
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
