import asyncio
import pandas as pd
import numpy as np
import json
import os
import sys
import time
from datetime import datetime, timedelta
from loguru import logger
import aiohttp
import hmac
import hashlib
import base64
import urllib.parse

# 确保项目根目录在路径中
sys.path.append(os.getcwd())
# 同时也支持同目录导入
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入指纹管理器
from src.research.fingerprint_manager import FingerprintManager

# 尝试加载配置
try:
    # 尝试作为包导入
    from src.research.config import (
        DINGTALK_TOKEN, DINGTALK_SECRET,
        PIR_THRESHOLD, VOL_SPIKE_THRESHOLD, PUMP_THRESHOLD, SHADOW_THRESHOLD
    )
except ImportError:
    try:
        # 尝试直接导入 (如果在同一目录下)
        from config import (
            DINGTALK_TOKEN, DINGTALK_SECRET,
            PIR_THRESHOLD, VOL_SPIKE_THRESHOLD, PUMP_THRESHOLD, SHADOW_THRESHOLD
        )
    except ImportError:
        logger.warning("Config not found, using defaults.")
        DINGTALK_TOKEN = ""
        DINGTALK_SECRET = ""
        PIR_THRESHOLD = 1.2
        VOL_SPIKE_THRESHOLD = 6.0
        PUMP_THRESHOLD = 1.2
        SHADOW_THRESHOLD = 1.2

class BinanceMMTracer:
    def __init__(self):
        self.base_url = "wss://fstream.binance.com/ws"
        self.symbols_data = {} # {symbol: {'klines': deque, 'sum_vol': float}}
        self.max_klines = 30   # 保持最近 30 分钟数据用于计算均值
        self.alert_log = "logs/mm_binance_alerts.log"
        os.makedirs("logs", exist_ok=True)
        self.kline_processed_count = 0  
        self.raw_packet_count = 0      # 新增：接收到的原始数据包统计
        self.has_received_first = False# 新增：是否收到过数据的标志
        self.preload_done = False      # 新增：预加载是否完成的标志
        self.start_time = time.time()
        self.session = None            # 共享 session
        self.semaphore = asyncio.Semaphore(20) # 限制并发 API 请求数
        
        # 初始化指纹管理器
        self.fingerprint_manager = FingerprintManager()
        
        # 配置日志
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(self.alert_log, rotation="10 MB", level="SUCCESS", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

    async def get_active_symbols(self):
        """获取所有交易中的 USDT 永续合约"""
        async with self.session.get("https://fapi.binance.com/fapi/v1/exchangeInfo") as resp:
            data = await resp.json()
            symbols = [
                s['symbol'] for s in data['symbols'] 
                if s['status'] == 'TRADING' and s['symbol'].endswith('USDT') and s['contractType'] == 'PERPETUAL'
            ]
            return [s.lower() for s in symbols]

    async def send_dingtalk_msg(self, content):
        """发送钉钉告警消息"""
        if not DINGTALK_TOKEN:
            return
            
        timestamp = str(round(time.time() * 1000))
        
        # 处理 DINGTALK_TOKEN 是完整 URL 的情况
        if DINGTALK_TOKEN.startswith("http"):
            url = DINGTALK_TOKEN
        else:
            url = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}"
        
        if DINGTALK_SECRET:
            secret_enc = DINGTALK_SECRET.encode('utf-8')
            string_to_sign = '{}\n{}'.format(timestamp, DINGTALK_SECRET)
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            connector = "&" if "?" in url else "?"
            url += f"{connector}timestamp={timestamp}&sign={sign}"

        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": f"【币安主力监控】\n{content}"
            }
        }
        
        try:
            async with self.session.post(url, json=data, headers=headers) as resp:
                res = await resp.text()
                logger.debug(f"DingTalk response: {res}")
        except Exception as e:
            logger.error(f"Failed to send DingTalk message: {e}")

    async def fetch_history(self, symbol):
        """为单个币种抓取 30 根历史 K 线"""
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            "symbol": symbol.upper(),
            "interval": "1m",
            "limit": self.max_klines
        }
        async with self.semaphore:
            try:
                # 稍微增加一点随机延迟，避免瞬间突发所有请求
                await asyncio.sleep(np.random.uniform(0.1, 0.5))
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        history = []
                        for k in data:
                            history.append({'v': float(k[5]), 'c': float(k[4])})
                        return symbol, history
                    elif resp.status == 429:
                        logger.warning(f"Rate limited (429) for {symbol}. Will retry later...")
                        return symbol, []
                    else:
                        logger.warning(f"Failed to fetch history for {symbol}: {resp.status}")
                        return symbol, []
            except Exception as e:
                logger.error(f"Error fetching history for {symbol}: {e}")
                return symbol, []

    async def preload_all_history(self, symbols):
        """并发预加载所有币种的历史数据"""
        logger.info(f"🚀 Starting history backfill for {len(symbols)} symbols...")
        tasks = [self.fetch_history(s) for s in symbols]
        results = await asyncio.gather(*tasks)
        
        count = 0
        for symbol, history in results:
            if history:
                self.symbols_data[symbol] = history
                count += 1
        
        self.preload_done = True
        logger.success(f"✅ History backfill complete. Loaded history for {count}/{len(symbols)} symbols.")

    def process_kline(self, symbol, k):
        """处理单条 K 线并检测指纹"""
        # 数据结构: [t, o, h, l, c, v, T, q, n, V, Q, B]
        # 我们需要: c, v, h, o, q (quote volume)
        try:
            self.raw_packet_count += 1
            if not self.has_received_first:
                self.has_received_first = True
                logger.info(f"✅ 数据流已激活! 从 {symbol.upper()} 收到第一个数据包")

            close = float(k['c'])
            high = float(k['h'])
            low = float(k['l'])
            open_p = float(k['o'])
            vol = float(k['v'])
            quote_vol = float(k['q'])
            is_closed = k['x'] # 是否是闭合 K 线
            
            if not is_closed:
                return # 仅处理闭合分钟 K 线以保证准确性

            if symbol not in self.symbols_data:
                self.symbols_data[symbol] = []
            
            history = self.symbols_data[symbol]
            history.append({'v': vol, 'c': close})
            if len(history) > self.max_klines:
                history.pop(0)

            if len(history) < 20: 
                # 每积累 5 分钟打印一次进度，减少日志量
                if len(history) % 5 == 0:
                    logger.debug(f"{symbol.upper()}: Baseline data accumulating ({len(history)}/20)...")
                return # 历史数据不足，不进行预警分析

            self.kline_processed_count += 1

            # --- 指纹计算逻辑 ---
            # 1. 成交量均值
            avg_vol = sum(h['v'] for h in history[:-1]) / (len(history) - 1)
            vol_spike = vol / avg_vol if avg_vol > 0 else 0
            
            # 2. 价格变化
            price_pct = (close - open_p) / open_p * 100
            
            # 3. PIR (价格冲击比) -> 涨幅 / (成交额 (百万USDT))
            # 预估净流: 如果涨，视为正流
            est_flow_m = quote_vol / 1e6
            pir = price_pct / est_flow_m if est_flow_m > 0.01 else 0 # 过滤极小额
            
            # 4. 影线分析
            upper_shadow = (high - max(open_p, close)) / close * 100
            lower_shadow = (min(open_p, close) - low) / close * 100
            
            # 5. 正资金流入占比 (基于最近5分钟)
            recent_history = history[-5:] if len(history) >=5 else history
            positive_flows = sum(1 for h in recent_history if h['c'] > h.get('open', h['c'])) / len(recent_history)
            
            # 6. 大单占比模拟 (基于成交额大小)
            is_big_order = quote_vol > 5000  # 成交额 > 5000 USDT 视为大单
            big_order_ratio = 1.0 if is_big_order else 0.0
            
            # 7. 综合判定预警 ---
            # 基础告警条件 (原有逻辑)
            is_ignition = (vol_spike > VOL_SPIKE_THRESHOLD) and (price_pct > PUMP_THRESHOLD)
            is_high_pir = (pir > PIR_THRESHOLD) and (price_pct > 0.5)
            
            # 实时指标，用于指纹匹配
            real_time_metrics = {
                "pir": pir,
                "vol_spike": vol_spike,
                "price_pct": price_pct,
                "positive_flow_ratio": positive_flows,
                "big_order_ratio": big_order_ratio,
                "upper_shadow": upper_shadow,
                "lower_shadow": lower_shadow
            }
            
            # 检查是否符合指纹特征 (主力拉盘起爆点)
            is_fingerprint_match, match_score = self.fingerprint_manager.is_valid_fingerprint(symbol, real_time_metrics)
            
            if is_fingerprint_match:
                # 主力拉盘起爆点告警 - 中文文案
                msg = (f"🚀 [🔥 主力拉盘起爆点] {symbol.upper()} | 匹配得分: {match_score}/100 | "
                       f"价格: {price_pct:+.2f}% | PIR: {pir:.2f} | "
                       f"成交量峰值: {vol_spike:.1f}x | 正资金流入: {positive_flows:.1%} | "
                       f"大单: {'是' if is_big_order else '否'} | 上影线: {upper_shadow:.2f}%")
                
                logger.success(msg)
                # 异步推送钉钉，使用更醒目的告警格式
                asyncio.create_task(self.send_dingtalk_msg(f"🔥🔥🔥 {msg}"))
                print(f"\a\a\a") # 连续蜂鸣提示
            elif is_ignition or is_high_pir:
                # 普通 MM 告警 - 中文文案
                score = 0
                if is_ignition: score += 50
                if is_high_pir: score += 30
                if upper_shadow > SHADOW_THRESHOLD: score += 20
                
                # 只有得分超过40分时才发送通知
                if score > 40:
                    msg = (f"⚠️  [主力监控告警] {symbol.upper()} | 得分: {score} | "
                           f"价格: {price_pct:+.2f}% | PIR: {pir:.2f} | "
                           f"成交量峰值: {vol_spike:.1f}x | 上影线: {upper_shadow:.2f}%")
                    
                    logger.success(msg)
                    # 异步推送钉钉
                    asyncio.create_task(self.send_dingtalk_msg(msg))
                    print(f"\a") # 终端蜂鸣提示 (如果支持)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    async def heartbeat(self):
        """报告状态。前2分钟每10秒报一次，之后每分钟一次"""
        count = 0
        while True:
            interval = 10 if count < 12 else 60 
            await asyncio.sleep(interval)
            count += 1
            
            uptime = str(timedelta(seconds=int(time.time() - self.start_time)))
            if not self.preload_done:
                status = "📥 正在预加载历史数据..."
            else:
                status = "🔥 正在监控" if self.kline_processed_count > 0 else "⏳ 等待新K线..."
            
            logger.info(f"💓 {status} | 运行时间: {uptime} | 处理K线数: {self.kline_processed_count} | 原始数据包: {self.raw_packet_count}")

    async def run_forever(self):
        """持续运行的 WebSocket 监听主循环"""
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self.heartbeat()) 
        while True:
            try:
                symbols = await self.get_active_symbols()
                
                # 初始预加载
                if not self.preload_done:
                    await self.preload_all_history(symbols)
                
                logger.info(f"✅ 连接成功. 正在监控 {len(symbols)} 个币安永续合约...")
                
                # 币安 WebSocket 限制：单个连接最多 200 个 streams
                # 我们分批订阅
                batch_size = 150
                tasks = []
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i : i + batch_size]
                    tasks.append(self.listen_batch(batch))
                
                await asyncio.gather(*tasks)
                
            except Exception as e:
                logger.error(f"❌ 主循环崩溃: {e}. 10秒后重试...")
                await asyncio.sleep(10)

    async def listen_batch(self, batch):
        """监听一批币种的数据流"""
        streams = "/".join([f"{s}@kline_1m" for s in batch])
        url = f"{self.base_url}/{streams}"
        
        async with self.session.ws_connect(url) as ws:
            logger.info(f"📡 Subscribed to batch of {len(batch)} symbols. Waiting for data...")
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if 'data' in data: # 复合流格式
                        symbol = data['data']['s'].lower()
                        kline = data['data']['k']
                        self.process_kline(symbol, kline)
                    else: # 单一流格式 (虽然我们用的是复合)
                        symbol = data['s'].lower()
                        kline = data['k']
                        self.process_kline(symbol, kline)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        logger.warning("Batch connection closed. Reconnecting...")

if __name__ == "__main__":
    tracer = BinanceMMTracer()
    try:
        asyncio.run(tracer.run_forever())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
