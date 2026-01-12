import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import aiohttp
import os
import sys
from loguru import logger

# 添加项目根目录到路径
sys.path.append(os.getcwd())

class LightMakerAnalyzer:
    def __init__(self, symbol="LIGHTUSDT"):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        # 将输出目录改为同级的 data 目录
        self.output_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.output_dir, exist_ok=True)

    async def fetch_agg_trades(self, start_time, end_time):
        """
        获取指定时段的 aggTrades
        """
        all_trades = []
        current_start = start_time
        
        async with aiohttp.ClientSession() as session:
            while current_start < end_time:
                # 每次最多获取 1000 条，或者按时间窗口获取
                # aggTrades 接口支持 startTime 和 endTime
                # 注意：startTime 和 endTime 间隔不能超过 1 小时
                temp_end = min(current_start + 3600000, end_time) 
                
                url = f"{self.base_url}/fapi/v1/aggTrades"
                params = {
                    "symbol": self.symbol,
                    "startTime": current_start,
                    "endTime": temp_end,
                    "limit": 1000
                }
                
                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data:
                                all_trades.extend(data)
                                if len(data) == 1000:
                                    current_start = data[-1]['T'] + 1
                                    continue
                            
                        elif response.status in [429, 418]:
                            logger.warning(f"Rate limited ({response.status}). Sleeping for 30s...")
                            await asyncio.sleep(30)
                            continue
                        else:
                            logger.error(f"Error fetching data: {response.status}")
                            await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Request exception: {e}")
                    await asyncio.sleep(5)
                
                current_start = temp_end + 1
                print(f"   进度: {datetime.fromtimestamp(current_start/1000)} | 已采集: {len(all_trades)} 条", end='\r')
                await asyncio.sleep(0.5) # 增加延迟以确安全

        return all_trades

    def process_trades(self, trades_data, period_name):
        """
        处理原始数据并聚合为分钟级别
        """
        if not trades_data:
            logger.warning(f"No data for {period_name}")
            return None

        df = pd.DataFrame(trades_data)
        # 字段映射: p=price, q=qty, T=timestamp, m=isBuyerMaker
        df['price'] = df['p'].astype(float)
        df['qty'] = df['q'].astype(float)
        df['timestamp'] = pd.to_datetime(df['T'], unit='ms')
        df['is_taker_buy'] = ~df['m'] # isBuyerMaker 为 False 表示卖方是 Maker，则买方是 Taker
        df['amount'] = df['price'] * df['qty']

        # 设置索引
        df.set_index('timestamp', inplace=True)

        # 聚合 1 分钟数据
        ohlcv = df['price'].resample('1min').ohlc()
        volume = df['qty'].resample('1min').sum()
        quote_volume = df['amount'].resample('1min').sum()
        
        # 区分买卖盘
        taker_buy_vol = df[df['is_taker_buy']]['qty'].resample('1min').sum().fillna(0)
        taker_sell_vol = df[~df['is_taker_buy']]['qty'].resample('1min').sum().fillna(0)
        
        # 大单识别 (假设 > $5000 为大单，视行情调整)
        whale_threshold = 5000
        whale_buy_vol = df[(df['is_taker_buy']) & (df['amount'] > whale_threshold)]['qty'].resample('1min').sum().fillna(0)
        whale_sell_vol = df[(~df['is_taker_buy']) & (df['amount'] > whale_threshold)]['qty'].resample('1min').sum().fillna(0)

        result = pd.concat([ohlcv, volume, quote_volume, taker_buy_vol, taker_sell_vol, whale_buy_vol, whale_sell_vol], axis=1)
        result.columns = ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 'taker_buy_vol', 'taker_sell_vol', 'whale_buy_vol', 'whale_sell_vol']
        
        # 计算指标
        result['net_flow'] = (result['taker_buy_vol'] - result['taker_sell_vol']) * result['close']
        result['cum_net_flow'] = result['net_flow'].cumsum()
        result['whale_net_flow'] = (result['whale_buy_vol'] - result['whale_sell_vol']) * result['close']
        result['cum_whale_flow'] = result['whale_net_flow'].cumsum()
        
        # 导出结果
        file_path = f"{self.output_dir}/{period_name}_processed.csv"
        result.to_csv(file_path)
        logger.info(f"Saved processed data to {file_path}")
        return result

    async def analyze(self):
        # 时段 1: 2025-12-18 00:00 至 2025-12-22 23:59
        p1_start = int(datetime(2025, 12, 18, 0, 0).timestamp() * 1000)
        p1_end = int(datetime(2025, 12, 22, 23, 59).timestamp() * 1000)
        
        # 时段 2: 2025-12-30 00:00 至 2026-01-02 23:59
        p2_start = int(datetime(2025, 12, 30, 0, 0).timestamp() * 1000)
        p2_end = int(datetime(2026, 1, 2, 23, 59).timestamp() * 1000)

        logger.info(f"开始抓取 P1 数据: 2025-12-18 至 2025-12-22")
        p1_raw = await self.fetch_agg_trades(p1_start, p1_end)
        p1_df = self.process_trades(p1_raw, "period1")

        logger.info(f"开始抓取 P2 数据: 2025-12-30 至 2026-01-02")
        p2_raw = await self.fetch_agg_trades(p2_start, p2_end)
        p2_df = self.process_trades(p2_raw, "period2")
        
        return p1_df, p2_df

if __name__ == "__main__":
    analyzer = LightMakerAnalyzer()
    asyncio.run(analyzer.analyze())
