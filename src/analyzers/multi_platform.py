from typing import Dict, List
import pandas as pd
from src.utils.logger import logger

class MultiPlatformAnalyzer:
    """
    Aggregates signals from multiple exchanges.
    """
    
    def analyze_signals(self, platform_metrics: Dict[str, dict], symbol: str = "UNKNOWN", df_5m: pd.DataFrame = None, df_1h: pd.DataFrame = None) -> List[dict]:
        """
        platform_metrics: { 'binance': {'cumulative_net_flow': ..., 'buy_sell_ratio': ...}, ... }
        """
        signals = []
        
        # 0. Multi-Timeframe Trend Confirmation
        trend_5m = "NEUTRAL"
        trend_1h = "NEUTRAL"
        
        if df_5m is not None and not df_5m.empty:
            # Simple MA trend or Price vs MA
            # Assuming df has 'close' and maybe 'ma' if computed, or compute here
            # Let's compute a quick SMA20 if not present
            close = df_5m['close'].iloc[-1]
            sma20 = df_5m['close'].rolling(20).mean().iloc[-1]
            if close > sma20:
                trend_5m = "BULLISH"
            elif close < sma20:
                trend_5m = "BEARISH"
                
        if df_1h is not None and not df_1h.empty:
            close = df_1h['close'].iloc[-1]
            sma20 = df_1h['close'].rolling(20).mean().iloc[-1]
            if close > sma20:
                trend_1h = "BULLISH"
            elif close < sma20:
                trend_1h = "BEARISH"

        # 1. Global Sync Bullish (A+)
        # Logic: All valid platforms Positive Flow & Ratio > 1.15
        all_positive = True
        all_strong_buy = True
        count_valid = len(platform_metrics)
        
        for p, m in platform_metrics.items():
            if m.get('cumulative_net_flow', 0) <= 0:
                all_positive = False
            if m.get('buy_sell_ratio', 0) <= 1.15:
                all_strong_buy = False
            
        # Require majority valid (>=3) and All of them are positive
        if count_valid >= 3 and all_positive and all_strong_buy: 
             # Check Trend Alignment
             is_aligned = True
             if trend_5m == "BEARISH" or trend_1h == "BEARISH":
                 is_aligned = False # Contra-trend signal
             
             if is_aligned:
                     signals.append({
                         'symbol': symbol,
                         'type': '全球协同看涨 (Global Sync Bullish)',
                         'grade': 'B+',
                         'desc': '主力全平台吸筹，市场做多情绪一致 (多周期共振)。'
                     })

        # 2. Global Sync Bearish (DISABLED)
        # Logic: All valid platforms Negative Flow & Buy/Sell Ratio < 0.85
        # all_negative = True
        # all_strong_sell = True
        
        # for p, m in platform_metrics.items():
        #     if m.get('cumulative_net_flow', 0) >= 0:
        #         all_negative = False
        #     if m.get('buy_sell_ratio', 1.0) >= 0.85:
        #         all_strong_sell = False
                
        # if count_valid >= 3 and all_negative and all_strong_sell:
        #      # Check Trend Alignment (Bearish)
        #      is_aligned = True
        #      if trend_5m == "BULLISH" or trend_1h == "BULLISH":
        #          is_aligned = False
                 
        #      if is_aligned:
        #              signals.append({
        #                  'symbol': symbol,
        #                  'type': '全球协同出货 (Global Sync Bearish)',
        #                  'grade': 'B+',
        #                  'desc': '主力全平台出货，市场做空情绪一致 (多周期共振)。'
        #              })

        # 3. US Institutional Accumulation (A)
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

        # 4. Derivatives Hedging (B) -> Requires OI data (Not implemented yet, placeholder)
        
        # 5. Single Platform Trap (C)
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
