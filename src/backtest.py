import asyncio
import pandas as pd
import numpy as np
import itertools
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

sys.path.append(os.getcwd())

from src.config import Config
from src.connectors.binance import BinanceConnector
from src.processors.data_processor import DataProcessor
from src.strategies.entry_exit import EntryExitStrategy
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.utils.logger import logger

class Backtester:
    def __init__(self, symbol: str, days: int = 3, connector: BinanceConnector = None):
        self.symbol = symbol
        self.days = days
        self.connector = connector
        self.strategy = EntryExitStrategy()
        self.taker_analyzer = TakerFlowAnalyzer(window=50)
        self.trades = []
        self.balance = 10000.0
        self.initial_balance = 10000.0
        self.position = None
        self.should_close_connector = False
    
    async def prepare_data(self):
        print(f"🔄 Fetching {self.days} days of data for {self.symbol}...")
        
        if not self.connector:
            self.connector = BinanceConnector()
            self.should_close_connector = True
            await self.connector.initialize()
        
        try:
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=self.days)).timestamp() * 1000)
            
            all_candles = []
            current_start = start_time
            
            while current_start < end_time:
                candles = await self.connector.exchange.fetch_ohlcv(
                    self.symbol, '1m', since=current_start, limit=1000
                )
                if not candles:
                    break
                all_candles.extend(candles)
                current_start = candles[-1][0] + 60000
                print(f"   Fetched {len(candles)} candles...", end='\r')
                await asyncio.sleep(0.1)
                
                if len(candles) < 1000:
                    break
            
            print(f"\n✅ Fetched {len(all_candles)} 1m candles.")
            
            df = pd.DataFrame(all_candles, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume'
            ])
            
            return df
        finally:
            if self.should_close_connector and self.connector:
                await self.connector.close()
                self.connector = None
            
    async def prepare_data_v2(self):
        print(f"🔄 Fetching {self.days} days of data for {self.symbol}...")
        
        if not self.connector:
            self.connector = BinanceConnector()
            self.should_close_connector = True
            await self.connector.initialize()
        
        try:
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=self.days)).timestamp() * 1000)
            
            all_raw_data = []
            current_start = start_time
            
            while current_start < end_time:
                limit = 1000
                params = {
                    'symbol': self.symbol.replace('/', ''),
                    'interval': '1m',
                    'startTime': current_start,
                    'limit': limit
                }
                
                klines = await self.connector.exchange.public_get_klines(params=params)
                
                if not klines:
                    break
                    
                all_raw_data.extend(klines)
                
                last_close_time = int(klines[-1][6])
                current_start = last_close_time + 1
                
                print(f"   Fetched {len(klines)} candles...", end='\r')
                # 增加请求间隔，避免触发API限流
                await asyncio.sleep(Config.RATE_LIMIT_DELAY)
                
                if len(klines) < limit:
                    break
            
            print(f"\n✅ Fetched {len(all_raw_data)} 1m candles.")
            
            df = pd.DataFrame(all_raw_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                'quote_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 
                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['timestamp'] = pd.to_numeric(df['timestamp'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            self.df_1m = df
            
            self.df_5m = self.resample_data(self.df_1m, '5min')
            self.df_1h = self.resample_data(self.df_1m, '1h')
        finally:
            if self.should_close_connector and self.connector:
                await self.connector.close()
                self.connector = None

        
    def resample_data(self, df, rule):
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

    def run(self, print_results=True):
        if print_results:
            print("🚀 Starting Backtest...")
        
        self.df_1m = self.taker_analyzer.analyze_df_batch(self.df_1m)
        
        for i in range(50, len(self.df_1m)):
            current_bar = self.df_1m.iloc[i]
            current_time = self.df_1m.index[i]
            
            if self.position:
                self.check_exit(current_bar, current_time)
            
            if not self.position:
                self.check_entry(i, current_time)
                
        if print_results:
            self.print_results()

    def check_exit(self, bar, timestamp):
        pos = self.position
        side = pos['side']
        entry = pos['entry_price']
        sl = pos['sl']
        tp = pos['tp']
        
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
        else:
            if bar['high'] >= sl:
                exit_price = sl
                reason = "SL"
            elif bar['low'] <= tp:
                exit_price = tp
                reason = "TP"
                
        if exit_price:
            if side == 'LONG':
                pnl = (exit_price - entry) / entry * pos['size']
            else:
                pnl = (entry - exit_price) / entry * pos['size']
                
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
        row = self.df_1m.iloc[index]
        metrics = {
            'cumulative_net_flow': row.get('cumulative_net_flow', 0),
            'buy_sell_ratio': row.get('buy_sell_ratio', 1.0),
            'current_price': row['close'],
            'support_low': row['close'] * 0.98,
            'resistance_high': row['close'] * 1.02,
            'atr': row['close'] * 0.01
        }
        
        atr_period = 14
        if index > atr_period:
            high = self.df_1m['high'].iloc[index-atr_period:index+1]
            low = self.df_1m['low'].iloc[index-atr_period:index+1]
            tr = high - low
            metrics['atr'] = tr.mean()
            
            metrics['support_low'] = low.min()
            metrics['resistance_high'] = high.max()
            
        platform_metrics = {'binance': metrics}
        
        consensus = "NEUTRAL"
        flow = metrics['cumulative_net_flow']
        if flow > Config.STRATEGY_MIN_TOTAL_FLOW: consensus = "看涨"
        elif flow < -Config.STRATEGY_MIN_TOTAL_FLOW: consensus = "看跌"
        
        df_5m_slice = self.df_5m[self.df_5m.index <= timestamp]
        df_1h_slice = self.df_1h[self.df_1h.index <= timestamp]
        
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
            price = rec['price']
            sl = rec['stop_loss']
            tp = rec['take_profit']
            side = rec['side']
            
            risk_amt = 1000
            dist = abs(price - sl)
            if dist == 0: return
            
            size = risk_amt / dist
            notional = size * price
            
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

    def calculate_max_drawdown(self) -> float:
        if not self.trades:
            return 0.0
        
        balance_curve = [self.initial_balance]
        for trade in self.trades:
            balance_curve.append(balance_curve[-1] + trade['pnl'])
        
        max_drawdown = 0.0
        peak = balance_curve[0]
        
        for balance in balance_curve:
            if balance > peak:
                peak = balance
            else:
                drawdown = (peak - balance) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        return max_drawdown

    def grid_search(self, param_grid: Dict) -> Dict:
        best_params = None
        best_winrate = 0.0
        best_results = None
        
        total_combinations = 1
        for values in param_grid.values():
            total_combinations *= len(values)
        
        # 限制参数组合数
        max_combinations = Config.STRATEGY_LEARNING_MAX_PARAM_COMBINATIONS
        if total_combinations > max_combinations:
            logger.info(f"⚠️  参数组合数 {total_combinations} 超过限制，将只测试前 {max_combinations} 个组合")
        
        current_combo = 0
        
        # 生成所有参数组合并限制数量
        all_combinations = list(itertools.product(*param_grid.values()))[:max_combinations]
        total_to_test = len(all_combinations)
        
        for params in all_combinations:
            param_dict = dict(zip(param_grid.keys(), params))
            current_combo += 1
            
            self.strategy = EntryExitStrategy(**param_dict)
            self.trades = []
            self.balance = self.initial_balance
            self.position = None
            
            self.run(print_results=False)
            
            if self.trades:
                winrate = len([t for t in self.trades if t['pnl'] > 0]) / len(self.trades)
                
                if winrate > best_winrate:
                    best_winrate = winrate
                    best_params = param_dict
                    best_results = {
                        'winrate': winrate,
                        'total_trades': len(self.trades),
                        'total_pnl': sum(t['pnl'] for t in self.trades),
                        'max_drawdown': self.calculate_max_drawdown()
                    }
        
        return {
            'best_params': best_params,
            'best_results': best_results
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
        max_drawdown = self.calculate_max_drawdown()
        
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PnL: ${total_pnl:,.2f}")
        print(f"Max Drawdown: {max_drawdown:.2%}")
        print("="*50)
