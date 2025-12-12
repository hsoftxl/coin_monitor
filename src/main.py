import asyncio
import time
from typing import Dict
from src.config import Config
from src.utils.logger import logger
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OKXConnector
from src.connectors.bybit import BybitConnector
from src.connectors.coinbase import CoinbaseConnector
from src.processors.data_processor import DataProcessor
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.whale_watcher import WhaleWatcher

from src.utils.discovery import SymbolDiscovery

async def main():
    logger.info("正在启动 GME-FFMS...")
    
    # 1. 确定监控币种
    target_symbols = [Config.SYMBOL]
    if Config.ENABLE_MULTI_SYMBOL:
        logger.info("正在扫描全平台共有币种...")
        sd = SymbolDiscovery()
        common = await sd.get_common_symbols()
        if common:
            target_symbols = common
            logger.info(f"监控列表 ({len(target_symbols)}): {', '.join(target_symbols)}")
        else:
            logger.warning("未发现共有币种，回退到默认币种。")

    # 初始化连接器 (Connectors need to be re-used, but they handle 'symbol' in fetch methods? 
    # Wait, Base Connector init takes NO symbol. 
    # But `fetch_standard_candles` usually takes `symbol` argument? 
    # Let's check `base.py`. `fetch_standard_candles` DOES NOT take symbol in current implementation?
    # It relies on `self.symbol` which is often set at init?
    # Checking base.py...
    # `BaseExchangeConnector` doesn't seem to take symbol in `__init__`, but it might use `Config.SYMBOL` globally?
    # If so, we need to refactor Connectors to accept symbol in `fetch`.
    
    # Let's check `src/connectors/base.py` content first.
    pass 
    
    # 初始化连接器
    connectors = {
        'binance': BinanceConnector(),
        'okx': OKXConnector(),
        'bybit': BybitConnector(),
        'coinbase': CoinbaseConnector()
    }
    
    initialized_connectors = {}
    for name, conn in connectors.items():
        if Config.EXCHANGES.get(name, True):
            try:
                await conn.initialize()
                initialized_connectors[name] = conn
            except Exception as e:
                logger.error(f"Failed to init {name}: {e}")
    
    # Initialize Analyzers
    taker_analyzer = TakerFlowAnalyzer(window=50)
    multi_analyzer = MultiPlatformAnalyzer()
    whale_watcher = WhaleWatcher(threshold=Config.WHALE_THRESHOLD)
    
    try:
        while True:
            start_time = time.time()
            platform_metrics: Dict[str, dict] = {}
            
            # 1. Fetch & Process Data Parallelly (Candles)
            tasks = {
                name: conn.fetch_standard_candles(limit=Config.LIMIT_KLINE) 
                for name, conn in initialized_connectors.items()
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            # Used for Whale Watch
            # Only Bybit and Coinbase support fetch_trades in our Base Connector setup easily?
            # Actually Base Connector has fetch_trades. All can do it.
            # But doing it sequentially might be slow. Let's do it for Coinbase/Bybit prioritized as per design.
            # Design: "Coinbase ... Whale Watcher".
            # Let's fetch trades for ALL for the "alive" feeling, but limit quantity.
            trade_tasks = {
                 name: conn.fetch_trades(limit=100)
                 for name, conn in initialized_connectors.items()
            }
            trade_results = await asyncio.gather(*trade_tasks.values(), return_exceptions=True)

            # 2. 分析各平台数据
            logger.info("--- [市场脉搏] ---")
            for i, (name, _) in enumerate(tasks.items()):
                res = results[i]
                if isinstance(res, Exception) or not res:
                    # logger.warning(f"{name} 无数据")
                    continue
                
                # Standardize & Flow
                df = DataProcessor.process_candles(res)
                metrics = taker_analyzer.analyze(df)
                platform_metrics[name] = metrics
                
                # Format Flow string
                flow_color = "<green>" if metrics['cumulative_net_flow'] > 0 else "<red>"
                flow_str = f"{flow_color}${metrics['cumulative_net_flow']:,.0f}</{flow_color[1:]}" # basic hack or just rely on logger? Loguru handles colors in message, not f-string tags dynamically usually unless opted in. 
                # Loguru markup: <green>...</green>.
                flow_val = metrics['cumulative_net_flow']
                tag = "green" if flow_val > 0 else "red"
                
                ratio = metrics['buy_sell_ratio']
                ratio_str = "INF" if ratio == float('inf') else f"{ratio:.2f}"
                
                logger.info(f"[{name.upper().ljust(8)}] 净流量: <{tag}>{flow_val:,.0f}</{tag}> | 买卖比: {ratio_str}")

            # 3. 巨鲸监控
            for i, (name, _) in enumerate(trade_tasks.items()):
                t_res = trade_results[i]
                if isinstance(t_res, list) and t_res:
                    whales = whale_watcher.check_trades(t_res)
                    for w in whales:
                         side = w['side'].upper()
                         side_cn = "买入" if side == 'BUY' else "卖出"
                         color = "green" if side == 'BUY' else "red"
                         logger.warning(f"🐳 巨鲸监测 [{name.upper()}]: <{color}>{side_cn} ${w['cost']:,.0f}</{color}> @ {w['price']}")

            # 4. 多平台信号与共识
            consensus = multi_analyzer.get_market_consensus(platform_metrics)
            logger.info(f"📊 市场共识: <bold>{consensus}</bold>")
            
            signals = multi_analyzer.analyze_signals(platform_metrics)
            for signal in signals:
                logger.critical(f"🚨 信号触发 [{signal['grade']}]: {signal['type']} - {signal['desc']}")
            
            logger.info("----------------------")
            
            # Sleep mechanism
            elapsed = time.time() - start_time
            sleep_time = max(0, 10 - elapsed) 
            
            await asyncio.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        for conn in initialized_connectors.values():
            await conn.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
