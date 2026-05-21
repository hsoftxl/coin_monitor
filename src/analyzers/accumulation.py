import pandas as pd
import time
from typing import Dict, Optional
from src.config import Config
from src.utils.logger import logger
from src.utils.indicators import (
    is_obv_rising,
    calculate_cmf,
    calculate_price_position,
    calculate_volume_profile_poc,
    is_close_to_poc,
    calculate_buying_pressure
)


class AccumulationAnalyzer:
    """
    庄家吸筹检测器

    检测逻辑：
    1. 价格处于近期低位（Price Position < 0.35）
    2. 成交量显著暴增（Volume Ratio ≥ 2.2x）
    3. OBV 持续上升（最近 N 根 K 线）
    4. CMF > 0（资金净流入）
    5. 买方压力 > 0.5（收盘在K线上半部分，非出货）
    6. 可选：价格接近 Volume Profile POC 支撑区

    与 EarlyPumpAnalyzer 的区别：
    - EarlyPumpAnalyzer 检测"价格已经开始拉升+放量"（突破信号）
    - AccumulationAnalyzer 检测"价格未动但量暴增+资金流入"（吸筹信号）

    两者互补：吸筹信号出现在拉升之前，拉盘信号确认拉升开始。
    """

    def __init__(self):
        self.vol_multiplier = Config.ACCUMULATION_VOL_MULTIPLIER
        self.vol_lookback = Config.ACCUMULATION_VOL_LOOKBACK
        self.obv_rising_bars = Config.ACCUMULATION_OBV_RISING_BARS
        self.cmf_period = Config.ACCUMULATION_CMF_PERIOD
        self.price_position_lookback = Config.ACCUMULATION_PRICE_POSITION_LOOKBACK
        self.price_position_threshold = Config.ACCUMULATION_PRICE_POSITION_THRESHOLD
        self.min_volume_usdt = Config.ACCUMULATION_MIN_VOLUME_USDT
        self.enable_poc_filter = Config.ACCUMULATION_ENABLE_POC_FILTER
        self.poc_threshold = Config.ACCUMULATION_POC_THRESHOLD
        self.cooldown_sec = Config.ACCUMULATION_COOLDOWN_SEC
        self.max_vol_multiplier = Config.ACCUMULATION_MAX_VOL_MULTIPLIER
        self.price_stability_ratio = Config.ACCUMULATION_PRICE_STABILITY_RATIO

        self.cooldowns: Dict[str, float] = {}

    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        检测庄家吸筹信号

        Args:
            df: K线数据（推荐 15m 或 1h）
            symbol: 交易对符号

        Returns:
            信号字典或 None
        """
        if df is None or df.empty:
            return None

        required_bars = max(
            self.vol_lookback + 1,
            self.price_position_lookback,
            self.cmf_period + 1,
            self.obv_rising_bars + 1
        )
        if len(df) < required_bars:
            return None

        now = time.time()
        if symbol in self.cooldowns:
            if now - self.cooldowns[symbol] < self.cooldown_sec:
                return None

        from src.utils.dataframe_helpers import get_latest_values
        latest_rows = get_latest_values(df, n=2)
        if latest_rows[0] is None or latest_rows[1] is None:
            return None

        current = latest_rows[0]
        prev = latest_rows[1]

        close_price = current['close']
        volume = current['volume']
        prev_close = prev['close']

        if close_price <= 0 or prev_close <= 0:
            return None

        # 1. Volume Ratio Check
        hist_df = df.iloc[-(self.vol_lookback + 1):-1]
        avg_vol = hist_df['volume'].mean()
        if avg_vol <= 0:
            return None

        vol_ratio = volume / avg_vol

        if vol_ratio < self.vol_multiplier:
            return None

        if vol_ratio > self.max_vol_multiplier:
            return None

        # 2. Volume absolute threshold check
        if volume < self.min_volume_usdt:
            return None

        # 3. Price Stability Check (not dumping)
        if close_price < prev_close * self.price_stability_ratio:
            return None

        # 4. OBV Rising Check
        if not is_obv_rising(df, self.obv_rising_bars):
            return None

        # 5. Price Position Check (low zone)
        price_position = calculate_price_position(df, self.price_position_lookback)
        if price_position is None or price_position >= self.price_position_threshold:
            return None

        # 6. CMF Check (money inflow)
        cmf = calculate_cmf(df, self.cmf_period)
        if cmf is None or cmf <= 0:
            return None

        # 7. Buying Pressure Check (close in upper half = buying, not distribution)
        buying_pressure = calculate_buying_pressure(df)
        if buying_pressure is None or buying_pressure <= 0.5:
            return None

        # 8. Optional: POC proximity check
        poc_price = None
        poc_distance = None
        if self.enable_poc_filter:
            poc_price, poc_distance = calculate_volume_profile_poc(df)
            if not is_close_to_poc(poc_distance, self.poc_threshold):
                return None

        # All conditions met - accumulation signal!
        self.cooldowns[symbol] = now

        desc_parts = [
            f"庄家吸筹特征",
            f"量比 {vol_ratio:.1f}x",
            f"OBV连续{self.obv_rising_bars}根上升",
            f"CMF +{cmf:.3f}",
            f"价格位置 {(price_position*100):.0f}% (低位)"
        ]
        if poc_price is not None:
            desc_parts.append(f"POC支撑 ${poc_price:.4f}")

        grade = self._calculate_grade(vol_ratio, cmf, price_position, buying_pressure)

        return {
            'type': 'ACCUMULATION',
            'grade': grade,
            'desc': " | ".join(desc_parts),
            'vol_ratio': vol_ratio,
            'cmf': cmf,
            'price_position': price_position,
            'buying_pressure': buying_pressure,
            'price': close_price,
            'volume': volume,
            'poc_price': poc_price,
            'poc_distance': poc_distance
        }

    def _calculate_grade(
        self,
        vol_ratio: float,
        cmf: float,
        price_position: float,
        buying_pressure: float
    ) -> str:
        score = 0

        if vol_ratio >= 4.0:
            score += 3
        elif vol_ratio >= 3.0:
            score += 2
        else:
            score += 1

        if cmf >= 0.15:
            score += 3
        elif cmf >= 0.05:
            score += 2
        elif cmf > 0:
            score += 1

        if price_position <= 0.15:
            score += 3
        elif price_position <= 0.25:
            score += 2
        else:
            score += 1

        if buying_pressure >= 0.8:
            score += 2
        elif buying_pressure >= 0.65:
            score += 1

        if score >= 9:
            return 'A+'
        elif score >= 6:
            return 'A'
        else:
            return 'B+'