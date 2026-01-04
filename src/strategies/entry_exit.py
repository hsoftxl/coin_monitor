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

    def evaluate(self, platform_metrics: Dict[str, dict], consensus: str, signals: List[dict], symbol: str, df_5m: object = None, df_1h: object = None) -> Dict:
        """
        Evaluate market conditions to generate entry/exit signals.
        Supports multi-timeframe trend confirmation.
        """
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
        
        # Trend Analysis (5m & 1h)
        trend_5m = "NEUTRAL"
        trend_1h = "NEUTRAL"
        
        if df_5m is not None and not df_5m.empty:
            close = df_5m['close'].iloc[-1]
            sma20 = df_5m['close'].rolling(20).mean().iloc[-1]
            if close > sma20: trend_5m = "BULLISH"
            elif close < sma20: trend_5m = "BEARISH"
            
        if df_1h is not None and not df_1h.empty:
            close = df_1h['close'].iloc[-1]
            sma20 = df_1h['close'].rolling(20).mean().iloc[-1]
            if close > sma20: trend_1h = "BULLISH"
            elif close < sma20: trend_1h = "BEARISH"
            
        has_strong_signal = any(s.get('grade') in ('A+', 'A') for s in signals)
        bullish_consensus = '看涨' in consensus
        bearish_consensus = '看跌' in consensus
        
        now = time.time()
        last_ts = self.last_action_time.get(symbol, 0)
        if last_ts and now - last_ts < self.min_interval_sec:
            return {'action': None, 'symbol': symbol}
            
        # Update Consensus Streak with Direction Reset
        streak_data = self.consensus_streak.get(symbol, {'count': 0, 'direction': 'NEUTRAL'})
        current_direction = 'NEUTRAL'
        if bullish_consensus: current_direction = 'BULLISH'
        elif bearish_consensus: current_direction = 'BEARISH'
        
        if current_direction != 'NEUTRAL':
            if current_direction == streak_data['direction']:
                streak_data['count'] += 1
            else:
                streak_data['count'] = 1
                streak_data['direction'] = current_direction
        else:
            streak_data['count'] = 0
            streak_data['direction'] = 'NEUTRAL'
            
        self.consensus_streak[symbol] = streak_data
        streak = streak_data['count']
        
        midband_ok = True
        if self.require_midband and support > 0 and resistance > 0:
            mid = (support + resistance) / 2.0
            if bullish_consensus and current_price < mid:
                midband_ok = False
            if bearish_consensus and current_price > mid:
                midband_ok = False
        
        # ENTRY LOGIC
        action = None
        side = None
        reason = None
        
        # Long Entry
        if bullish_consensus and (has_strong_signal or (total_flow >= self.min_total_flow and avg_ratio >= self.min_ratio)):
            # MTF Confirmation: Don't go long if 1h trend is bearish
            mtf_ok = True
            if trend_1h == "BEARISH": 
                mtf_ok = False
            
            if midband_ok and streak >= self.min_consensus_bars and mtf_ok:
                action = 'ENTRY'
                side = 'LONG'
                reason = f'Bullish Consensus + Trend({trend_1h})'

        # Short Entry (DISABLED)
        # elif bearish_consensus and total_flow <= -self.min_total_flow:
        #     # MTF Confirmation: Don't go short if 1h trend is bullish
        #     mtf_ok = True
        #     if trend_1h == "BULLISH": 
        #         mtf_ok = False
                
        #     if midband_ok and streak >= self.min_consensus_bars and mtf_ok:
        #         action = 'ENTRY'
        #         side = 'SHORT'
        #         reason = f'Bearish Consensus + Trend({trend_1h})'
        
        if action:
            sl = None
            tp = None
            
            # Dynamic Risk Reward Optimization
            # Default RR = 2.0 / 1.5 = 1.33
            # If trend is aligned (e.g. 5m matches signal), boost TP
            rr_boost = 1.0
            if side == 'LONG' and trend_5m == "BULLISH": rr_boost = 1.2
            if side == 'SHORT' and trend_5m == "BEARISH": rr_boost = 1.2
            
            final_sl_mult = self.atr_sl_mult
            final_tp_mult = self.atr_tp_mult * rr_boost
            
            if atr > 0:
                if side == 'LONG':
                    sl = current_price - final_sl_mult * atr
                    tp = current_price + final_tp_mult * atr
                else:
                    sl = current_price + final_sl_mult * atr
                    tp = current_price - final_tp_mult * atr
            
            # Fallback to Support/Resistance
            if sl is None:
                if side == 'LONG' and support > 0: sl = support * 0.99
                elif side == 'SHORT' and resistance > 0: sl = resistance * 1.01
                
            if tp is None:
                if side == 'LONG' and resistance > 0: tp = resistance
                elif side == 'SHORT' and support > 0: tp = support
            
            # Final sanity check for SL/TP
            if sl and tp:
                self.last_action_time[symbol] = now
                return {
                    'action': action, 
                    'side': side, 
                    'price': current_price, 
                    'stop_loss': sl, 
                    'take_profit': tp, 
                    'reason': reason, 
                    'symbol': symbol,
                    'trend_1h': trend_1h,
                    'trend_5m': trend_5m
                }

        # EXIT LOGIC
        if support > 0 and current_price < support:
            self.last_action_time[symbol] = now
            return {'action': 'EXIT', 'side': 'LONG', 'price': current_price, 'reason': 'break_support', 'symbol': symbol}
        if resistance > 0 and current_price > resistance and not bullish_consensus:
            self.last_action_time[symbol] = now
            return {'action': 'EXIT', 'side': 'SHORT', 'price': current_price, 'reason': 'break_resistance', 'symbol': symbol}
            
        return {'action': None, 'symbol': symbol}
    
    
    def compute_position(self, rec: Dict, volatility_level: str = 'NORMAL') -> Dict:
        """
        计算仓位大小 (集成 PositionManager)
        """
        price = rec.get('price')
        sl = rec.get('stop_loss')
        symbol = rec.get('symbol')
        tp = rec.get('take_profit')
        
        if not price or not sl or not symbol:
            return {}
            
        # 使用 PositionManager 替代旧的硬编码逻辑
        from src.utils.position_manager import PositionManager
        pm = PositionManager() # 会自动读取 Config 配置
        
        pos_info = pm.calculate_position_size(
            symbol=symbol,
            entry_price=price,
            stop_loss=sl,
            volatility_level=volatility_level,
            take_profit=tp
        )
        
        if not pos_info.get('allowed', False):
            from src.utils.logger import logger
            logger.warning(f"[{symbol}] 仓位限制: {pos_info.get('reason')}")
            return {}
            
        return {
            'size_base': pos_info['size'],
            'notional_usd': pos_info['notional'],
            'risk_amount': pos_info['risk_amount'],
            'pct_of_account': pos_info['pct_of_account']
        }
