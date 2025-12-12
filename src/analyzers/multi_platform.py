from typing import Dict, List
import pandas as pd
from src.utils.logger import logger

class MultiPlatformAnalyzer:
    """
    Aggregates signals from multiple exchanges.
    """
    
    def analyze_signals(self, platform_metrics: Dict[str, dict], symbol: str = "UNKNOWN") -> List[dict]:
        """
        platform_metrics: { 'binance': {'cumulative_net_flow': ..., 'buy_sell_ratio': ...}, ... }
        """
        signals = []
        
        # 1. Global Sync Bullish (A+)
        # Logic: All 4 Positive Flow & Ratio > 1.15
        all_positive = True
        all_strong_buy = True
        count_valid = 0
        
        for p, m in platform_metrics.items():
            if m.get('cumulative_net_flow', 0) <= 0:
                all_positive = False
            if m.get('buy_sell_ratio', 0) <= 1.15:
                all_strong_buy = False
            count_valid += 1
            
        if count_valid >= 3 and all_positive and all_strong_buy: # Relaxed slightly for robustness or strict 4? Design says "All 4".
             # If we have 4 platforms, check 4. If one down, maybe 3? 
             # Design: "All 4".
             if count_valid == 4:
                 signals.append({
                     'symbol': symbol,
                     'type': '全球协同看涨 (Global Sync Bullish)',
                     'grade': 'A+',
                     'desc': '主力全平台吸筹，市场做多情绪一致。'
                 })

        # 2. US Institutional Accumulation (A)
        # Coinbase Net Flow >> others & Whale Buy Concentrated
        cb_flow = platform_metrics.get('coinbase', {}).get('cumulative_net_flow', 0)
        others_avg_flow = 0
        others_count = 0
        for p, m in platform_metrics.items():
            if p != 'coinbase':
                others_avg_flow += m.get('cumulative_net_flow', 0)
                others_count += 1
        
        if others_count > 0:
            avg_flow = others_avg_flow / others_count
            if cb_flow > (avg_flow * 1.5) and cb_flow > 1000000: # Arbitrary large number threshold or relative?
                # Design says "Significantly higher".
                signals.append({
                     'symbol': symbol,
                     'type': '美资机构吸筹 (US Institutional Accumulation)',
                     'grade': 'A',
                     'desc': 'Coinbase 领涨，机构资金流入显著。'
                 })

        # 3. Derivatives Hedging (B) -> Requires OI data (Not implemented yet, placeholder)
        
        # 4. Single Platform Trap (C)
        # Binance/OKX Buy High, Coinbase/Bybit Sell (Negative Flow)
        binance_flow = platform_metrics.get('binance', {}).get('cumulative_net_flow', 0)
        coinbase_flow = platform_metrics.get('coinbase', {}).get('cumulative_net_flow', 0)
        
        if binance_flow > 0 and coinbase_flow < 0:
             signals.append({
                 'symbol': symbol,
                 'type': '单平台诱多 (Single Platform Long Trap)',
                 'grade': 'C',
                 'desc': '东方交易所买入，西方交易所卖出。警惕诱多。'
             })
             
        return signals

    def get_market_consensus(self, platform_metrics: Dict[str, dict]) -> str:
        """
        Returns a high-level summary string based on flows.
        """
        positive_flows = 0
        negative_flows = 0
        total_flow = 0.0
        
        for p, m in platform_metrics.items():
            flow = m.get('cumulative_net_flow', 0)
            total_flow += flow
            if flow > 1000: positive_flows += 1
            elif flow < -1000: negative_flows += 1
            
        if positive_flows == 4:
            return "强力看涨 (全平台净流入)"
        elif negative_flows == 4:
            return "强力看跌 (全平台净流出)"
        elif total_flow > 50000000: # 50M
             return f"倾向看涨 (总净流入: ${total_flow/1000000:.1f}M)"
        elif total_flow < -50000000:
             return f"倾向看跌 (总净流出: ${abs(total_flow)/1000000:.1f}M)"
        else:
             return "震荡/分歧 (无明确方向)"
