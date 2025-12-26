import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

from src.config import Config
from src.connectors.binance import BinanceConnector
from src.processors.data_processor import DataProcessor
from src.strategies.entry_exit import EntryExitStrategy
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.utils.logger import logger

class Backtester:
    def __init__(self, symbol: str, days: int = 3):
        self.symbol = symbol
        self.days = days
        self.connector = BinanceConnector()
        self.strategy = EntryExitStrategy()
        self.taker_analyzer = TakerFlowAnalyzer(window=50)
        self.trades = []
        self.balance = 10000.0  # Initial Balance
        self.initial_balance = 10000.0
        self.position = None # {'side': 'LONG', 'entry_price': ..., 'size': ..., 'sl': ..., 'tp': ...}

    async def prepare_data(self):
        print(f"🔄 Fetching {self.days} days of data for {self.symbol}...")
        await self.connector.initialize()
        
        # 1. Fetch 1m data (Main timeframe)
        # Binance limit is usually 1000, so we might need pagination for multiple days
        # For simplicity, we fetch max allowed or looped
        # 1 day = 1440 mins. 3 days = 4320.
        # We need a loop to fetch history.
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=self.days)).timestamp() * 1000)
        
        all_candles = []
        current_start = start_time
        
        while current_start < end_time:
            # Limit 1000 per request
            candles = await self.connector.exchange.fetch_ohlcv(
                self.symbol, '1m', since=current_start, limit=1000
            )
            if not candles:
                break
            all_candles.extend(candles)
            current_start = candles[-1][0] + 60000 # Next minute
            print(f"   Fetched {len(candles)} candles...", end='\r')
            await asyncio.sleep(0.1)
            
        print(f"\n✅ Fetched {len(all_candles)} 1m candles.")
        
        # Convert to DF
        # DataProcessor expects objects, but fetch_ohlcv returns lists [ts, o, h, l, c, v]
        # We need to adapt or modify DataProcessor.
        # But DataProcessor.process_candles iterates and expects objects with .close etc if it's CCXT specific?
        # Actually in src/processors/data_processor.py it seems to access .close (Attribute access)
        # But fetch_ohlcv returns raw list.
        # Let's check how main.py does it. 
        # main.py uses conn.fetch_standard_candles which returns list of objects or dicts?
        # Let's check src/connectors/binance.py fetch_standard_candles
        # It calls public_get_klines and returns raw list [ts, o, h, l, c, v...] 
        # Wait, DataProcessor.process_candles might be designed for objects?
        # Let's look at DataProcessor code again if possible. 
        # But here, let's just convert manually to DF directly to be safe.
        
        df = pd.DataFrame(all_candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        ])
        
        # We need quote volume and taker buy volume which are not in standard ohlcv list from ccxt?
        # CCXT fetch_ohlcv usually returns [timestamp, open, high, low, close, volume].
        # It misses Taker Buy Volume which is critical for our strategy.
        # So we MUST use `fetch_standard_candles` from connector which uses raw API to get extra fields.
        
        await self.connector.close()
        
        # RE-FETCH using fetch_standard_candles to get full data
        # But fetch_standard_candles in binance connector takes limit.
        # We need to implement pagination manually or loop.
        # Let's just fix the loop to use fetch_standard_candles
        pass

    async def prepare_data_v2(self):
        print(f"🔄 Fetching {self.days} days of data for {self.symbol}...")
        await self.connector.initialize()
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=self.days)).timestamp() * 1000)
        
        all_raw_data = []
        current_start = start_time
        
        while current_start < end_time:
            # We use the raw fetch method from connector if available or construct params
            # BinanceConnector.fetch_standard_candles uses params={'interval': ...}
            # We need to pass startTime/endTime to paginate
            
            # We can use the exchange object directly with params
            limit = 1000
            params = {
                'symbol': self.symbol.replace('/', ''),
                'interval': '1m',
                'startTime': current_start,
                'limit': limit
            }
            
            # Use raw public_get_klines for binance to match connector logic
            # Connector uses: self.exchange.public_get_klines(params)
            # Response: [[open_time, open, high, low, close, volume, close_time, quote_asset_volume, number_of_trades, taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore], ...]
            
            klines = await self.connector.exchange.public_get_klines(params=params)
            
            if not klines:
                break
                
            all_raw_data.extend(klines)
            
            last_close_time = int(klines[-1][6])
            current_start = last_close_time + 1
            
            print(f"   Fetched {len(klines)} candles...", end='\r')
            await asyncio.sleep(0.1)
            
            if len(klines) < limit:
                break
            
        print(f"\n✅ Fetched {len(all_raw_data)} 1m candles.")
        
        # Manually construct DF to match DataProcessor expectations (or just use it directly)
        # DataProcessor.process_candles handles the conversion from this raw list format?
        # Let's check DataProcessor.process_candles in src/processors/data_processor.py
        # It seems it expects a list of objects or a specific format.
        # To be safe and consistent with TakerFlowAnalyzer, let's create the DF manually here with correct columns.
        
        # Binance Raw Columns:
        # 0: Open time, 1: Open, 2: High, 3: Low, 4: Close, 5: Volume, 6: Close time, 
        # 7: Quote asset volume, 8: Number of trades, 9: Taker buy base asset volume, 10: Taker buy quote asset volume
        
        df = pd.DataFrame(all_raw_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
            'quote_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Convert types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 
                       'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        self.df_1m = df
        
        # 2. Resample
        self.df_5m = self.resample_data(self.df_1m, '5min')
        self.df_1h = self.resample_data(self.df_1m, '1h')
        
        await self.connector.close()

        
    def resample_data(self, df, rule):
        # Ensure index is datetime
        df_resampled = df.resample(rule, closed='left', label='left').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'quote_volume': 'sum',
            'taker_buy_base_asset_volume': 'sum',
            'taker_buy_quote_asset_volume': 'sum',
            'number_of_trades': 'sum'
        }).dropna()
        return df_resampled

    def run(self):
        print("🚀 Starting Backtest...")
        
        # Simulate bar by bar
        # We need to simulate the "Live" environment.
        # At index i, we only know data up to i.
        
        # Optimization: Pre-calculate indicators for the whole dataset to speed up
        # But for strategy logic that depends on 'current state', we step through.
        
        # Let's pre-calculate Taker Flow metrics for 1m
        self.df_1m = self.taker_analyzer.analyze_df_batch(self.df_1m)
        
        # Main Loop
        # Start from index 50 (warmup)
        for i in range(50, len(self.df_1m)):
            current_bar = self.df_1m.iloc[i]
            current_time = self.df_1m.index[i]
            
            # 1. Update Position (Check SL/TP first with High/Low of current bar)
            if self.position:
                self.check_exit(current_bar, current_time)
            
            # 2. If no position, check Entry
            if not self.position:
                self.check_entry(i, current_time)
                
        self.print_results()

    def check_exit(self, bar, timestamp):
        pos = self.position
        side = pos['side']
        entry = pos['entry_price']
        sl = pos['sl']
        tp = pos['tp']
        
        # Check SL/TP hit within the bar (High/Low)
        # Assumption: If both SL and TP are hit in same bar, assume SL hit (Conservative)
        
        exit_price = None
        pnl = 0
        reason = ""
        
        if side == 'LONG':
            if bar['low'] <= sl:
                exit_price = sl
                reason = "SL"
            elif bar['high'] >= tp:
                exit_price = tp
                reason = "TP"
        else: # SHORT
            if bar['high'] >= sl:
                exit_price = sl
                reason = "SL"
            elif bar['low'] <= tp:
                exit_price = tp
                reason = "TP"
                
        if exit_price:
            # Calculate PnL
            if side == 'LONG':
                pnl = (exit_price - entry) / entry * pos['size']
            else:
                pnl = (entry - exit_price) / entry * pos['size']
                
            # Fee (0.05% per side = 0.1% total)
            fee = pos['size'] * 0.001
            pnl -= fee
            
            self.balance += pnl
            self.trades.append({
                'entry_time': pos['time'],
                'exit_time': timestamp,
                'side': side,
                'entry_price': entry,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': (pnl / pos['size']) * 100,
                'reason': reason
            })
            self.position = None

    def check_entry(self, index, timestamp):
        # Prepare metrics dict for strategy (Mocking the multi-platform dict)
        # In backtest, we only use Binance data
        
        # Get slice for analysis
        df_slice = self.df_1m.iloc[:index+1]
        
        # Construct platform_metrics mock
        # We need computed metrics from TakerFlowAnalyzer (already in df columns if batch processed?)
        # TakerFlowAnalyzer usually returns a dict for the *last* candle. 
        # But we added analyze_df_batch to enrich DF.
        
        # Extract metrics from current row
        row = self.df_1m.iloc[index]
        metrics = {
            'cumulative_net_flow': row.get('cumulative_net_flow', 0),
            'buy_sell_ratio': row.get('buy_sell_ratio', 1.0),
            'current_price': row['close'],
            'support_low': row['close'] * 0.98, # Simplified support
            'resistance_high': row['close'] * 1.02, # Simplified resistance
            'atr': row['close'] * 0.01 # Simplified ATR if not computed
        }
        
        # Compute real ATR if possible or use rolling std
        # Let's use a quick ATR approx from High-Low
        # Proper ATR requires prev close. 
        # For speed, let's assume TakerFlowAnalyzer added 'atr' or we compute it.
        # Actually TakerFlowAnalyzer computes 'net_flow' etc. It doesn't compute ATR/Support.
        # Let's compute dynamic ATR here for better accuracy
        atr_period = 14
        if index > atr_period:
            # True Range
            high = self.df_1m['high'].iloc[index-atr_period:index+1]
            low = self.df_1m['low'].iloc[index-atr_period:index+1]
            close = self.df_1m['close'].iloc[index-atr_period:index+1]
            # Simple average of H-L for speed
            tr = high - low
            metrics['atr'] = tr.mean()
            
            # Simple Donchian Support/Resist
            metrics['support_low'] = low.min()
            metrics['resistance_high'] = high.max()
            
        platform_metrics = {'binance': metrics}
        
        # Consensus: In single platform backtest, consensus is just this platform
        consensus = "NEUTRAL"
        flow = metrics['cumulative_net_flow']
        if flow > Config.STRATEGY_MIN_TOTAL_FLOW: consensus = "看涨"
        elif flow < -Config.STRATEGY_MIN_TOTAL_FLOW: consensus = "看跌"
        
        # Get HTF Data slices
        # Find 5m candle corresponding to current time
        # df_5m index is start time. current_time is 1m start time.
        # We need the latest closed 5m candle relative to current_time.
        # 5m data includes current open bar? No, we should use closed bars to avoid lookahead.
        # So we take 5m bars where index < current_time.
        
        df_5m_slice = self.df_5m[self.df_5m.index <= timestamp]
        df_1h_slice = self.df_1h[self.df_1h.index <= timestamp]
        
        # Evaluate Strategy
        # Signals: Mocking signals. In backtest, we rely on Flow mostly.
        # We can trigger "Strong Signal" if Flow is very high
        signals = []
        if abs(flow) > Config.STRATEGY_MIN_TOTAL_FLOW * 2:
            signals.append({'grade': 'A', 'type': 'Strong Flow'})
            
        rec = self.strategy.evaluate(
            platform_metrics, 
            consensus, 
            signals, 
            self.symbol,
            df_5m=df_5m_slice,
            df_1h=df_1h_slice
        )
        
        if rec.get('action') == 'ENTRY':
            # Execute Entry
            price = rec['price']
            sl = rec['stop_loss']
            tp = rec['take_profit']
            side = rec['side']
            
            # Position Sizing (Fixed 1000 USD risk or 10% of balance)
            risk_amt = 1000 # Config.STRATEGY_RISK_USD
            # Calc size based on SL distance
            dist = abs(price - sl)
            if dist == 0: return
            
            size = risk_amt / dist
            notional = size * price
            
            # Cap notional
            if notional > 10000:
                size = 10000 / price
            
            self.position = {
                'side': side,
                'entry_price': price,
                'size': size,
                'sl': sl,
                'tp': tp,
                'time': timestamp
            }

    def print_results(self):
        print("\n" + "="*50)
        print(f"📊 Backtest Results for {self.symbol} ({self.days} days)")
        print("="*50)
        
        total_trades = len(self.trades)
        if total_trades == 0:
            print("No trades executed.")
            return
            
        wins = [t for t in self.trades if t['pnl'] > 0]
        losses = [t for t in self.trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / total_trades * 100
        total_pnl = sum(t['pnl'] for t in self.trades)
        
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate:     {win_rate:.2f}% ({len(wins)}W / {len(losses)}L)")
        print(f"Total PnL:    ${total_pnl:.2f}")
        print(f"Final Bal:    ${self.balance:.2f} ({(self.balance/self.initial_balance - 1)*100:.2f}%)")
        print("-" * 50)
        print("Latest 5 Trades:")
        for t in self.trades[-5:]:
            print(f"{t['entry_time']} {t['side']} PnL: ${t['pnl']:.2f} ({t['reason']})")
        print("="*50)

# Batch Analysis method injection for TakerFlowAnalyzer to speed up backtest
def analyze_df_batch(self, df: pd.DataFrame) -> pd.DataFrame:
    # Vectorized calculation of Cumulative Net Flow and Buy/Sell Ratio
    # This is a simplified version of the loop in analyze()
    
    # Taker Buy Base * Price ~= Taker Buy Quote (Approx)
    # Actually df has 'taker_buy_quote_asset_volume'
    
    buy_vol = df['taker_buy_quote_asset_volume']
    sell_vol = df['quote_volume'] - buy_vol # Approx total - buy = sell? 
    # Wait, quote_volume is Total. Taker Buy is subset.
    # Taker Sell = Total Volume - Taker Buy Volume? 
    # No, Total = Taker Buy + Taker Sell + Maker... 
    # Actually in Binance: 
    # Taker Buy Volume = Volume of trades where taker was buyer.
    # The rest is Taker Sell Volume (where taker was seller).
    # Total Volume = Taker Buy + Taker Sell.
    
    taker_sell_vol = df['quote_volume'] - buy_vol
    
    # Net Flow
    net_flow = buy_vol - taker_sell_vol
    
    # Cumulative Flow (Rolling window)
    df['cumulative_net_flow'] = net_flow.rolling(window=self.window).sum()
    
    # Buy Sell Ratio (Rolling)
    roll_buy = buy_vol.rolling(window=self.window).sum()
    roll_sell = taker_sell_vol.rolling(window=self.window).sum()
    df['buy_sell_ratio'] = roll_buy / roll_sell
    
    return df

TakerFlowAnalyzer.analyze_df_batch = analyze_df_batch


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ETH/USDT"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    bt = Backtester(symbol, days)
    try:
        asyncio.run(bt.prepare_data_v2())
        bt.run()
    except KeyboardInterrupt:
        pass
