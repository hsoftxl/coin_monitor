from typing import Dict, List
import numpy as np
import time
from src.config import Config

class EntryExitStrategy:
    def __init__(self, min_total_flow: float = None, min_ratio: float = None):
        self.min_total_flow = min_total_flow if min_total_flow is not None else Config.STRATEGY_MIN_TOTAL_FLOW
        self.min_ratio = min_ratio if min_ratio is not None else Config.STRATEGY_MIN_RATIO
        self.min_interval_sec = getattr(Config, 'STRATEGY_MIN_INTERVAL_SEC', 900)
        self.atr_sl_mult = getattr(Config, 'STRATEGY_ATR_SL_MULT', 1.5)
        self.atr_tp_mult = getattr(Config, 'STRATEGY_ATR_TP_MULT', 2.0)
        self.require_midband = getattr(Config, 'STRATEGY_REQUIRE_MIDBAND', True)
        self.min_consensus_bars = getattr(Config, 'STRATEGY_MIN_CONSENSUS_BARS', 2)
        self.last_action_time: Dict[str, float] = {}
        self.consensus_streak: Dict[str, int] = {}

    def evaluate(self, platform_metrics: Dict[str, dict], consensus: str, signals: List[dict], symbol: str) -> Dict:
        total_flow = sum(m.get('cumulative_net_flow', 0.0) for m in platform_metrics.values())
        ratios = [m.get('buy_sell_ratio', 0.0) for m in platform_metrics.values() if m.get('buy_sell_ratio') is not None]
        prices = [m.get('current_price', 0.0) for m in platform_metrics.values() if m.get('current_price') is not None]
        supports = [m.get('support_low', 0.0) for m in platform_metrics.values() if m.get('support_low') is not None]
        resistances = [m.get('resistance_high', 0.0) for m in platform_metrics.values() if m.get('resistance_high') is not None]
        atrs = [m.get('atr', 0.0) for m in platform_metrics.values() if m.get('atr') is not None]
        avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
        current_price = float(np.median(prices)) if prices else 0.0
        support = float(np.median(supports)) if supports else 0.0
        resistance = float(np.median(resistances)) if resistances else 0.0
        atr = float(np.median(atrs)) if atrs else 0.0
        has_strong_signal = any(s.get('grade') in ('A+', 'A') for s in signals)
        bullish = '看涨' in consensus
        bearish = '看跌' in consensus
        now = time.time()
        last_ts = self.last_action_time.get(symbol, 0)
        if last_ts and now - last_ts < self.min_interval_sec:
            return {'action': None, 'symbol': symbol}
        streak = self.consensus_streak.get(symbol, 0)
        if bullish:
            streak += 1
        elif bearish:
            streak += 1
        else:
            streak = 0
        self.consensus_streak[symbol] = streak
        midband_ok = True
        if self.require_midband and support > 0 and resistance > 0:
            mid = (support + resistance) / 2.0
            if bullish and current_price < mid:
                midband_ok = False
            if bearish and current_price > mid:
                midband_ok = False
        if bullish and (has_strong_signal or (total_flow >= self.min_total_flow and avg_ratio >= self.min_ratio)):
            if midband_ok and streak >= self.min_consensus_bars:
                sl = None
                tp = None
                if atr > 0:
                    sl = current_price - self.atr_sl_mult * atr
                    tp = current_price + self.atr_tp_mult * atr
                if sl is None and support > 0:
                    sl = support * 0.99
                if tp is None and resistance > 0:
                    tp = resistance
                self.last_action_time[symbol] = now
                return {'action': 'ENTRY', 'side': 'LONG', 'price': current_price, 'stop_loss': sl, 'take_profit': tp, 'reason': 'bullish_consensus', 'symbol': symbol}
        if bearish and total_flow <= -self.min_total_flow:
            if midband_ok and streak >= self.min_consensus_bars:
                sl = None
                tp = None
                if atr > 0:
                    sl = current_price + self.atr_sl_mult * atr
                    tp = current_price - self.atr_tp_mult * atr
                if sl is None and resistance > 0:
                    sl = resistance * 1.01
                if tp is None and support > 0:
                    tp = support
                self.last_action_time[symbol] = now
                return {'action': 'ENTRY', 'side': 'SHORT', 'price': current_price, 'stop_loss': sl, 'take_profit': tp, 'reason': 'bearish_consensus', 'symbol': symbol}
        if support > 0 and current_price < support:
            self.last_action_time[symbol] = now
            return {'action': 'EXIT', 'side': 'LONG', 'price': current_price, 'reason': 'break_support', 'symbol': symbol}
        if resistance > 0 and current_price > resistance and not bullish:
            self.last_action_time[symbol] = now
            return {'action': 'EXIT', 'side': 'SHORT', 'price': current_price, 'reason': 'break_resistance', 'symbol': symbol}
        return {'action': None, 'symbol': symbol}
    
    def compute_position(self, rec: Dict) -> Dict:
        price = rec.get('price')
        sl = rec.get('stop_loss')
        side = rec.get('side')
        if not price or not sl or not side:
            return {}
        risk_dist = price - sl if side == 'LONG' else sl - price
        if risk_dist <= 0:
            return {}
        size_base = Config.STRATEGY_RISK_USD / risk_dist
        notional = size_base * price
        if notional > Config.STRATEGY_MAX_NOTIONAL_USD:
            scale = Config.STRATEGY_MAX_NOTIONAL_USD / notional
            size_base *= scale
            notional = Config.STRATEGY_MAX_NOTIONAL_USD
        return {'size_base': size_base, 'notional_usd': notional}
