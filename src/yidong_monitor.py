import asyncio
import json
import aiohttp
import websockets
from datetime import datetime

# --- 配置区域 ---
MIN_VOLUME_USDT = 100000
PUMP_THRESHOLD_PCT = 1.0  # 调低阈值到1%，这样你更容易看到程序在动
BLACKLIST = ['UPUSDT', 'DOWNUSDT', 'BULLUSDT', 'BEARUSDT', 'BUSDUSDT', 'USDCUSDT']


class WhaleMonitor:
    def __init__(self):
        self.base_ws_url = "wss://stream.binance.com:9443/stream?streams="
        self.rest_url = "https://api.binance.com/api/v3/exchangeInfo"
        self.symbols = []
        self.msg_count = 0  # 统计收到的消息数量

    async def get_usdt_pairs(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [INFO] 正在获取币安所有交易对...")
        async with aiohttp.ClientSession() as session:
            async with session.get(self.rest_url) as response:
                data = await response.json()
                self.symbols = [
                    s['symbol'].lower() for s in data['symbols']
                    if s['symbol'].endswith('USDT')
                       and s['status'] == 'TRADING'
                       and s['symbol'] not in BLACKLIST
                ]
                print(f"[INFO] 成功获取 {len(self.symbols)} 个 USDT 交易对")

    async def stats_report(self):
        """每10秒打印一次运行状态，让你知道程序没死"""
        while True:
            await asyncio.sleep(10)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [HEARTBEAT] 过去10秒处理了 {self.msg_count} 条 K线更新数据...")
            self.msg_count = 0

    async def monitor(self):
        chunk_size = 200
        tasks = [self.stats_report()]  # 把统计任务加进去

        for i in range(0, len(self.symbols), chunk_size):
            chunk = self.symbols[i:i + chunk_size]
            streams = "/".join([f"{s}@kline_1m" for s in chunk])
            url = f"{self.base_ws_url}{streams}"
            tasks.append(self._connect_socket(url, i))

        await asyncio.gather(*tasks)

    async def _connect_socket(self, url, chunk_id):
        print(f"[INFO] 正在连接数据流分片 {chunk_id}...")
        try:
            async with websockets.connect(url) as websocket:
                print(f"[SUCCESS] 分片 {chunk_id} 连接成功，开始接收数据...")
                while True:
                    message = await websocket.recv()
                    self.msg_count += 1  # 增加计数
                    data = json.loads(message)
                    if 'data' in data:
                        self._process_kline(data['data'])
        except Exception as e:
            print(f"[ERROR] 分片 {chunk_id} 连接异常: {e}")
            await asyncio.sleep(5)

    def _process_kline(self, data):
        k = data['k']
        symbol = k['s']
        close_price = float(k['c'])
        open_price = float(k['o'])
        quote_volume = float(k['q'])
        is_closed = k['x']

        change_pct = ((close_price - open_price) / open_price) * 100

        # 如果涨幅大于 0.5% 就打印一条极简日志，让你知道它在扫哪些币 (可选关闭)
        # if change_pct > 0.5:
        #     print(f"  [Scanning] {symbol} | Change: {change_pct:.2f}% | Vol: {quote_volume:.0f}")

        if change_pct >= PUMP_THRESHOLD_PCT and quote_volume >= MIN_VOLUME_USDT:
            self._trigger_alert(symbol, change_pct, quote_volume, close_price, is_closed)

    def _trigger_alert(self, symbol, change, volume, price, is_closed):
        status = "🔴 已收盘" if is_closed else "⚡ 实时"
        print(f"\n{'=' * 40}")
        print(f"🚀 [主力拉盘告警] {symbol} {status}")
        print(f"⏰ 时间: {datetime.now().strftime('%H:%M:%S')}")
        print(f"📈 涨幅: +{change:.2f}% (当前分钟)")
        print(f"💰 成交: ${volume:,.0f} USDT")
        print(f"💲 价格: {price}")
        print(f"{'=' * 40}\n")


async def main():
    monitor = WhaleMonitor()
    await monitor.get_usdt_pairs()
    await monitor.monitor()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] 监控已停止")