import asyncio
import time
from typing import Dict, List
import pandas as pd
from loguru import logger
from src.config import Config
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OKXConnector
from src.connectors.bybit import BybitConnector
from src.connectors.coinbase import CoinbaseConnector
from src.processors.data_processor import DataProcessor
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.whale_watcher import WhaleWatcher
from src.utils.discovery import SymbolDiscovery

async def process_symbol(symbol: str, connectors: Dict, taker_analyzer, multi_analyzer, whale_watcher):
    """
    Process a single symbol across all exchanges.
    """
    # logger.info(f"Analyzing {symbol}...")
    
    # 1. Fetch Data
    # Fetch Candles
    tasks = {
        name: conn.fetch_standard_candles(symbol=symbol, limit=Config.LIMIT_KLINE) 
        for name, conn in connectors.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    # Fetch Trades (Best effort for Whale Watcher)
    trade_tasks = {
         name: conn.fetch_trades(symbol=symbol, limit=100)
         for name, conn in connectors.items()
    }
    trade_results = await asyncio.gather(*trade_tasks.values(), return_exceptions=True)

    platform_metrics: Dict[str, dict] = {}
    valid_data_count = 0
    
    # 2. Analyze Individual Platforms
    for i, (name, _) in enumerate(tasks.items()):
        res = results[i]
        if isinstance(res, Exception) or not res or len(res) < 5:
            # logger.warning(f"[{symbol}] {name} 无数据或数据不足: {res}")
            continue
        
        valid_data_count += 1
        
        # Standardize & Flow
        df = DataProcessor.process_candles(res)
        metrics = taker_analyzer.analyze(df)
        platform_metrics[name] = metrics
        
    if valid_data_count < 2:
        return # Skip if not enough data for consensus

    # 3. Consensus & Signals
    consensus = multi_analyzer.get_market_consensus(platform_metrics)
    
    # Log Output (Compact for multiple symbols)
    # Only log if there is significant activity or divergence? 
    # Or simple table row style.
    # [ETH/USDT] CONSENSUS: BULLISH | Bin: +10M | OKX: +5M ...
    
    log_parts = []
    total_flow = 0
    for name, m in platform_metrics.items():
        flow = m['cumulative_net_flow']
        total_flow += flow
        tag = "green" if flow > 0 else "red"
        # Shorten name: BINANCE->BIN
        short_name = name[:3].upper()
        log_parts.append(f"{short_name}:<{tag}>{flow/1000:.0f}k</{tag}>")
    
    # Determine consensus color
    cons_tag = "white"
    if "看涨" in consensus or "BULLISH" in consensus: cons_tag = "green"
    elif "看跌" in consensus or "BEARISH" in consensus: cons_tag = "red"
    
    logger.info(f"💰 <bold>{symbol.ljust(9)}</bold> | 共识: <{cons_tag}>{consensus.split('(')[0]}</{cons_tag}> | {' | '.join(log_parts)}")

    # 4. Signals
    signals = multi_analyzer.analyze_signals(platform_metrics, symbol=symbol)
    for signal in signals:
        logger.critical(f"🚨 [{symbol}] 信号触发 [{signal['grade']}]: {signal['type']} - {signal['desc']}")

    # 5. Whale Watcher
    for i, (name, _) in enumerate(trade_tasks.items()):
        t_res = trade_results[i]
        if isinstance(t_res, list) and t_res:
            whales = whale_watcher.check_trades(t_res)
            for w in whales:
                 side = w['side'].upper()
                 side_cn = "买入" if side == 'BUY' else "卖出"
                 color = "green" if side == 'BUY' else "red"
                 logger.warning(f"🐳 [{symbol}] 巨鲸监测 [{name.upper()}]: <{color}>{side_cn} ${w['cost']:,.0f}</{color}> @ {w['price']}")


async def main():
    logger.info("正在启动 GME-FFMS (多币种全监控模式)...")
    
    # 初始化连接器
    connectors = {
        'binance': BinanceConnector(),
        'okx': OKXConnector(),
        'bybit': BybitConnector(),
        'coinbase': CoinbaseConnector() # Coinbase usually has limited USDT pairs, might fail for some.
    }
    
    # Init
    initialized = {}
    for name, conn in connectors.items():
        try:
            await conn.initialize()
            initialized[name] = conn
        except Exception as e:
            logger.error(f"{name} 初始化失败: {e}")
            
    if not initialized:
        logger.error("无可用连接器，退出。")
        return

    # Coin Discovery
    target_symbols = [Config.SYMBOL]
    if Config.ENABLE_MULTI_SYMBOL:
        logger.info("正在扫描全平台共有币种...")
        sd = SymbolDiscovery()
        common = await sd.get_common_symbols()
        if common:
            # Filter top 20 alphabetically or by some criteria to avoid 27 taking too long if rate limited?
            # 27 is fine.
            target_symbols = common
            logger.info(f"✅ 监控列表 ({len(target_symbols)}): {', '.join(target_symbols)}")
        else:
            logger.warning("❌ 未发现共有币种，回退到默认币种。")

    taker_analyzer = TakerFlowAnalyzer(window=50)
    multi_analyzer = MultiPlatformAnalyzer()
    whale_watcher = WhaleWatcher(threshold=Config.WHALE_THRESHOLD) # $200k

    try:
        while True:
            cycle_start = time.time()
            logger.info(f"=== 开始新一轮扫描 ({len(target_symbols)} 币种) ===")
            
            # Process symbols in chunks of 5 to control concurrency
            chunk_size = 5
            for i in range(0, len(target_symbols), chunk_size):
                chunk = target_symbols[i:i + chunk_size]
                await asyncio.gather(*[
                    process_symbol(s, initialized, taker_analyzer, multi_analyzer, whale_watcher) 
                    for s in chunk
                ])
                # Small sleep between chunks to be nice to APIs
                await asyncio.sleep(1)

            elapsed = time.time() - cycle_start
            logger.info(f"=== 扫描完成，耗时 {elapsed:.1f}s ===")
            
            # Sleep mechanism
            # If 1m timeframe, we want to run every ~60s.
            sleep_time = max(5, 60 - elapsed)
            # logger.info(f"等待 {sleep_time:.0f}s ...")
            await asyncio.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("正在停止...")
    finally:
        for conn in initialized.values():
            await conn.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
