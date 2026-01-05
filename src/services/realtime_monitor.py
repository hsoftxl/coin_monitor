import asyncio
import json
import aiohttp
import websockets
import websockets.exceptions
from datetime import datetime
from typing import Optional, Dict, Any
from src.config import Config
from src.utils.logger import logger
from src.services.notification import NotificationService


class RealtimeMonitor:
    """
    Real-time WebSocket monitor for Binance 1m Kline streams.
    Supports both SPOT and FUTURES markets.
    """
    
    def __init__(self, notification_service: Optional[NotificationService] = None):
        # Spot WebSocket
        self.spot_ws_url = "wss://stream.binance.com:9443/stream?streams="
        # Futures WebSocket
        self.futures_ws_url = "wss://fstream.binance.com/stream?streams="
        
        self.rest_url = "https://api.binance.com/api/v3/exchangeInfo"
        self.futures_rest_url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        
        self.spot_symbols = []
        self.futures_symbols = []
        self.msg_count = 0
        self.notification_service = notification_service
        
        # Config
        self.pump_threshold = Config.REALTIME_PUMP_THRESHOLD
        self.min_volume = Config.REALTIME_MIN_VOLUME
        self.blacklist = Config.REALTIME_BLACKLIST
        
        self.enable_spot = Config.ENABLE_SPOT_MARKET
        self.enable_futures = Config.ENABLE_FUTURES_MARKET
        
        # Cooldown tracking (separate for spot/futures)
        self.cooldowns = {}
        self.cooldown_sec = 600  # 10 minutes
        
        # Connection health tracking
        self.connection_stats = {}  # {chunk_id: {'last_message_time': float, 'message_count': int, 'reconnect_count': int}}
        self.health_check_interval = 60  # Check health every 60 seconds

    async def get_spot_pairs(self):
        """Fetch all SPOT USDT trading pairs from Binance."""
        if not self.enable_spot:
            return
            
        logger.info("正在获取币安现货 USDT 交易对...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.rest_url) as response:
                    data = await response.json()
                    self.spot_symbols = [
                        s['symbol'].lower() for s in data['symbols']
                        if s['symbol'].endswith('USDT')
                           and s['status'] == 'TRADING'
                           and s['symbol'] not in self.blacklist
                    ]
                    logger.info(f"✅ 现货监控: 成功获取 {len(self.spot_symbols)} 个交易对")
        except Exception as e:
            logger.error(f"❌ 获取现货交易对失败: {e}")

    async def get_futures_pairs(self):
        """Fetch all FUTURES USDT trading pairs from Binance."""
        if not self.enable_futures:
            return
            
        logger.info("正在获取币安永续合约 USDT 交易对...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.futures_rest_url) as response:
                    data = await response.json()
                    self.futures_symbols = [
                        s['symbol'].lower() for s in data['symbols']
                        if s['symbol'].endswith('USDT')
                           and s['status'] == 'TRADING'
                           and s['contractType'] == 'PERPETUAL'
                           and s['symbol'] not in self.blacklist
                    ]
                    logger.info(f"✅ 合约监控: 成功获取 {len(self.futures_symbols)} 个交易对")
        except Exception as e:
            logger.error(f"❌ 获取合约交易对失败: {e}")

    async def stats_report(self):
        """Report statistics every 30 seconds and check connection health."""
        while True:
            await asyncio.sleep(30)
            spot_count = len(self.spot_symbols) if self.enable_spot else 0
            futures_count = len(self.futures_symbols) if self.enable_futures else 0
            logger.info(f"[实时监控] 过去30秒处理 {self.msg_count} 条数据 | 现货:{spot_count} 合约:{futures_count}")
            
            # Health check
            current_time = asyncio.get_event_loop().time()
            for conn_key, stats in self.connection_stats.items():
                time_since_last_msg = current_time - stats['last_message_time']
                if time_since_last_msg > 120:  # No message for 2 minutes
                    logger.warning(f"[实时监控] {conn_key} 健康检查: 已{int(time_since_last_msg)}秒未收到消息")
                if stats['reconnect_count'] > 5:
                    logger.warning(f"[实时监控] {conn_key} 健康检查: 重连次数过多 ({stats['reconnect_count']})")
            
            self.msg_count = 0

    async def start(self):
        """Main entry point to start monitoring."""
        await self.get_spot_pairs()
        await self.get_futures_pairs()
        
        tasks = [self.stats_report()]
        chunk_size = 200

        # Start SPOT WebSocket connections
        if self.enable_spot and self.spot_symbols:
            for i in range(0, len(self.spot_symbols), chunk_size):
                chunk = self.spot_symbols[i:i + chunk_size]
                streams = "/".join([f"{s}@kline_1m" for s in chunk])
                url = f"{self.spot_ws_url}{streams}"
                tasks.append(self._connect_socket(url, f"SPOT-{i // chunk_size}", 'spot'))

        # Start FUTURES WebSocket connections
        if self.enable_futures and self.futures_symbols:
            for i in range(0, len(self.futures_symbols), chunk_size):
                chunk = self.futures_symbols[i:i + chunk_size]
                streams = "/".join([f"{s}@kline_1m" for s in chunk])
                url = f"{self.futures_ws_url}{streams}"
                tasks.append(self._connect_socket(url, f"FUTURES-{i // chunk_size}", 'futures'))

        await asyncio.gather(*tasks)

    async def _connect_socket(self, url, chunk_id, market_type):
        """
        Connect to WebSocket and process messages with exponential backoff retry.
        
        Args:
            url: WebSocket URL
            chunk_id: Chunk identifier for logging
            market_type: 'spot' or 'futures'
        """
        logger.info(f"[实时监控] 正在连接 {market_type.upper()} 数据流 #{chunk_id}...")
        retry_delay = 5
        max_retry_delay = 60
        reconnect_count = 0
        
        # Initialize connection stats
        conn_key = f"{market_type}-{chunk_id}"
        if conn_key not in self.connection_stats:
            self.connection_stats[conn_key] = {
                'last_message_time': 0,
                'message_count': 0,
                'reconnect_count': 0,
                'last_health_check': 0
            }
        
        while True:
            try:
                # Set connection timeout
                async with websockets.connect(
                    url,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,  # Wait 10 seconds for pong
                    close_timeout=10
                ) as websocket:
                    logger.info(f"[实时监控] {market_type.upper()} #{chunk_id} 连接成功")
                    reconnect_count = 0
                    retry_delay = 5  # Reset retry delay on successful connection
                    
                    # Update connection stats
                    self.connection_stats[conn_key]['reconnect_count'] = reconnect_count
                    self.connection_stats[conn_key]['last_message_time'] = asyncio.get_event_loop().time()
                    
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            self.msg_count += 1
                            data = json.loads(message)
                            
                            # Update stats
                            self.connection_stats[conn_key]['message_count'] += 1
                            self.connection_stats[conn_key]['last_message_time'] = asyncio.get_event_loop().time()
                            
                            if 'data' in data:
                                await self._process_kline(data['data'], market_type)
                        except asyncio.TimeoutError:
                            # No message received in 30 seconds, send ping to check connection
                            logger.debug(f"[实时监控] {market_type.upper()} #{chunk_id} 30秒未收到消息，检查连接...")
                            try:
                                pong_waiter = await websocket.ping()
                                await asyncio.wait_for(pong_waiter, timeout=10)
                            except Exception:
                                logger.warning(f"[实时监控] {market_type.upper()} #{chunk_id} Ping失败，准备重连...")
                                break
                                
            except websockets.exceptions.ConnectionClosed:
                reconnect_count += 1
                self.connection_stats[conn_key]['reconnect_count'] = reconnect_count
                logger.warning(f"[实时监控] {market_type.upper()} #{chunk_id} 连接关闭，{retry_delay}秒后重连 (重连次数: {reconnect_count})...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff
                
            except Exception as e:
                reconnect_count += 1
                self.connection_stats[conn_key]['reconnect_count'] = reconnect_count
                logger.error(f"[实时监控] {market_type.upper()} #{chunk_id} 连接异常: {e}，{retry_delay}秒后重连 (重连次数: {reconnect_count})...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff

    async def _process_kline(self, data, market_type):
        """Process incoming kline data."""
        k = data['k']
        symbol = k['s']
        close_price = float(k['c'])
        open_price = float(k['o'])
        quote_volume = float(k['q'])
        is_closed = k['x']

        if open_price <= 0:
            return

        change_pct = ((close_price - open_price) / open_price) * 100

        # Check cooldown (separate for spot/futures)
        cooldown_key = f"{market_type}:{symbol}"
        now = asyncio.get_event_loop().time()
        if cooldown_key in self.cooldowns:
            if now - self.cooldowns[cooldown_key] < self.cooldown_sec:
                return

        # Trigger condition
        if change_pct >= self.pump_threshold and quote_volume >= self.min_volume:
            self.cooldowns[cooldown_key] = now
            await self._trigger_alert(symbol, change_pct, quote_volume, close_price, is_closed, market_type)

    async def _trigger_alert(self, symbol, change, volume, price, is_closed, market_type):
        """Send alert notification."""
        status = "🔴 已收盘" if is_closed else "⚡ 实时"
        market_label = "现货" if market_type == 'spot' else "永续合约"
        
        logger.critical(f"🚀 [{market_label}] {symbol} {status} | 涨幅: +{change:.2f}% | 成交: ${volume:,.0f}")
        
        if self.notification_service:
            data = {
                'symbol': symbol,
                'change_pct': change,
                'volume': volume,
                'price': price,
                'is_closed': is_closed,
                'market_type': market_type,
                'market_label': market_label
            }
            await self.notification_service.send_realtime_pump_alert(data)

