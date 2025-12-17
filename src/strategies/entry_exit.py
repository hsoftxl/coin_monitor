from typing import Dict, List
import numpy as np
from src.config import Config

class EntryExitStrategy:
    def __init__(self, min_total_flow: float = None, min_ratio: float = None):
        self.min_total_flow = min_total_flow if min_total_flow is not None else Config.STRATEGY_MIN_TOTAL_FLOW
        self.min_ratio = min_ratio if min_ratio is not None else Config.STRATEGY_MIN_RATIO

    def evaluate(self, platform_metrics: Dict[str, dict], consensus: str, signals: List[dict], symbol: str) -> Dict:
        total_flow = sum(m.get('cumulative_net_flow', 0.0) for m in platform_metrics.values())
        ratios = [m.get('buy_sell_ratio', 0.0) for m in platform_metrics.values() if m.get('buy_sell_ratio') is not None]
        prices = [m.get('current_price', 0.0) for m in platform_metrics.values() if m.get('current_price') is not None]
        supports = [m.get('support_low', 0.0) for m in platform_metrics.values() if m.get('support_low') is not None]
        resistances = [m.get('resistance_high', 0.0) for m in platform_metrics.values() if m.get('resistance_high') is not None]
        avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
        current_price = float(np.median(prices)) if prices else 0.0
        support = float(np.median(supports)) if supports else 0.0
        resistance = float(np.median(resistances)) if resistances else 0.0
        has_strong_signal = any(s.get('grade') in ('A+', 'A') for s in signals)
        bullish = '看涨' in consensus
        bearish = '看跌' in consensus
        if bullish and (has_strong_signal or (total_flow >= self.min_total_flow and avg_ratio >= self.min_ratio)):
            sl = support * 0.99 if support > 0 else None
            tp = resistance if resistance > 0 else None
            return {'action': 'ENTRY', 'side': 'LONG', 'price': current_price, 'stop_loss': sl, 'take_profit': tp, 'reason': 'bullish_consensus', 'symbol': symbol}
        if bearish and total_flow <= -self.min_total_flow:
            sl = resistance * 1.01 if resistance > 0 else None
            tp = support if support > 0 else None
            return {'action': 'ENTRY', 'side': 'SHORT', 'price': current_price, 'stop_loss': sl, 'take_profit': tp, 'reason': 'bearish_consensus', 'symbol': symbol}
        if support > 0 and current_price < support:
            return {'action': 'EXIT', 'side': 'LONG', 'price': current_price, 'reason': 'break_support', 'symbol': symbol}
        if resistance > 0 and current_price > resistance and not bullish:
            return {'action': 'EXIT', 'side': 'SHORT', 'price': current_price, 'reason': 'break_resistance', 'symbol': symbol}
        return {'action': None, 'symbol': symbol}
