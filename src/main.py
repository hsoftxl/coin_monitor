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
from src.analyzers.volume_spike import VolumeSpikeAnalyzer
from src.analyzers.spot_futures_analyzer import SpotFuturesAnalyzer
from src.analyzers.early_pump import EarlyPumpAnalyzer
from src.analyzers.panic_dump import PanicDumpAnalyzer
from src.utils.discovery import SymbolDiscovery
from src.services.notification import NotificationService
from src.services.realtime_monitor import RealtimeMonitor
from src.strategies.entry_exit import EntryExitStrategy
from src.analyzers.steady_growth import SteadyGrowthAnalyzer
from src.storage.persistence import Persistence

async def process_symbol(symbol: str, connectors: Dict, taker_analyzer, multi_analyzer, whale_watcher, vol_spike_analyzer, early_pump_analyzer, panic_dump_analyzer, steady_growth_analyzer, sf_analyzer, strategy, notification_service=None, persistence=None):
    """
    Process a single symbol across all exchanges.
    """
    # 0. Pre-filter: Check which exchanges support this symbol
    valid_connectors = {}
    for name, conn in connectors.items():
        try:
            if not (conn.exchange and conn.exchange.markets):
                continue
            if symbol in conn.exchange.symbols:
                valid_connectors[name] = conn
            elif name == 'coinbase':
                usd_symbol = symbol.replace('/USDT', '/USD')
                if usd_symbol in conn.exchange.symbols:
                    valid_connectors[name] = conn
        except Exception:
            pass
    
    if not valid_connectors:
        # No exchange supports this symbol, skip silently
        return
    
    # 1. Fetch Data (only from valid exchanges)
    # Fetch 1m Candles (main data)
    tasks = {
        name: conn.fetch_standard_candles(symbol=symbol, limit=Config.LIMIT_KLINE) 
        for name, conn in valid_connectors.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    
    # Fetch 24h Ticker (for Volume display)
    ticker_24h_vol = 0
    if valid_connectors:
        first_conn = list(valid_connectors.values())[0]
        try:
             ticker = await first_conn.fetch_ticker(symbol)
             ticker_24h_vol = ticker.get('quoteVolume', 0)
             # Fallback if quoteVolume is None/0 but baseVolume exists
             if not ticker_24h_vol and ticker.get('baseVolume') and ticker.get('last'):
                 ticker_24h_vol = ticker['baseVolume'] * ticker['last']
        except Exception:
             pass

    # Fetch Multi-Timeframe Data (for Resonance)
    df_res = None
    if Config.ENABLE_MULTI_TIMEFRAME and valid_connectors:
        # Use first available connector for MTF data
        first_conn = list(valid_connectors.values())[0]
        try:
            # Fetch Resonance Timeframe (15m)
            data_res = await first_conn.fetch_candles_timeframe(symbol, Config.MTF_RES_TIMEFRAME, limit=100)
            if data_res:
                df_res = DataProcessor.process_candles(data_res)
        except Exception as e:
            logger.debug(f"[{symbol}] 共振数据({Config.MTF_RES_TIMEFRAME})获取失败: {e}")
    
    # Fetch Spot-Futures Data (for correlation analysis)
    spot_df = None
    futures_df = None
    if Config.ENABLE_SPOT_FUTURES_CORRELATION and 'binance' in valid_connectors:
        try:
            # Fetch spot data (already have from main fetch above)
            # Fetch futures data (USDT perpetual)
            futures_symbol = symbol  # Most are same symbol for perpetuals
            conn = valid_connectors['binance']
            # Try to fetch from futures market
            # Note: This requires the exchange to support futures
            # For simplicity, we'll skip if not available
            pass  # Will implement if futures API available
        except Exception:
            pass
    
    # Fetch Trades (Best effort for Whale Watcher)
    trade_tasks = {
         name: conn.fetch_trades(symbol=symbol, limit=100)
         for name, conn in valid_connectors.items()
    }
    trade_results = await asyncio.gather(*trade_tasks.values(), return_exceptions=True)

    platform_metrics: Dict[str, dict] = {}
    valid_data_count = 0
    
    # Spot-Futures Correlation Analysis (using first valid platform)
    sf_correlation = None
    if Config.ENABLE_SPOT_FUTURES_CORRELATION and spot_df is not None and futures_df is not None:
        sf_correlation = sf_analyzer.analyze_correlation(spot_df, futures_df, symbol)
    
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
        
        # Volume Spike Analysis
        spike = vol_spike_analyzer.analyze(df, symbol)
        if spike:
             spike['vol_24h'] = ticker_24h_vol
             logger.warning(f"🔥 [{symbol}] 成交量暴增: {spike['ratio']:.1f}x (涨幅 {spike['price_change']:.2f}%)")
             if notification_service:
                 await notification_service.send_volume_spike_alert(spike, symbol)
                 
        # Whale Analysis (for Confirmation)
        current_whales = []
        if i < len(trade_results):
            t_res = trade_results[i]
            if isinstance(t_res, list) and t_res:
                current_whales = whale_watcher.check_trades(t_res)

        # Early Pump Analysis (Enhanced with Resonance + SF correlation + Whales)
        sf_strength = sf_correlation['strength'] if sf_correlation else None
        pump = early_pump_analyzer.analyze(
            df, 
            symbol,
            df_res=df_res,
            sf_strength=sf_strength,
            whales=current_whales
        )
        if pump:
             pump['vol_24h'] = ticker_24h_vol
             logger.critical(f"[{symbol}] {pump['desc']}")
             if notification_service:
                 await notification_service.send_early_pump_alert(pump, symbol)

        # Panic Dump Analysis (DISABLED)
        # dump = panic_dump_analyzer.analyze(
        #     df,
        #     symbol,
        #     df_res=df_res,
        #     sf_strength=sf_strength,
        #     whales=current_whales
        # )
        # if dump:
        #      logger.critical(f"[{symbol}] {dump['desc']}")
        #      if notification_service:
        #          await notification_service.send_panic_dump_alert(dump, symbol)

        # Steady Growth Analysis (Slow Track - 15m)
        steady = steady_growth_analyzer.analyze(df_res, symbol)
        if steady:
             steady['vol_24h'] = ticker_24h_vol
             logger.info(f"💎 [{symbol}] {steady['desc']}")
             if notification_service:
                 await notification_service.send_steady_growth_alert(steady, symbol)
        
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
    
    # 推送市场共识通知（强力看涨/看跌）
    if notification_service:
        await notification_service.send_consensus_alert(consensus, platform_metrics, symbol)

    # 4. Signals
    # 4. Signals
    signals = multi_analyzer.analyze_signals(platform_metrics, symbol=symbol, df_5m=df, df_1h=df_res)
    for signal in signals:
        logger.critical(f"🚨 [{symbol}] 信号触发 [{signal['grade']}]: {signal['type']} - {signal['desc']}")
        
        # 推送通知
        if notification_service:
            await notification_service.dispatch_signal(signal, platform_metrics, symbol)
        if persistence:
            persistence.save_signal(signal, platform_metrics, symbol)

    # 4.1 Strategy
    # 4.1 Strategy
    rec = strategy.evaluate(platform_metrics, consensus, signals, symbol, df_5m=df, df_1h=df_res)
    pos = strategy.compute_position(rec) if rec.get('action') else {}
    rec.update(pos)
    if rec.get('action'):
        logger.info(f"🎯 [{symbol}] 策略建议: {rec['action']} {rec['side']} @ {rec['price']:.4f} SL={rec.get('stop_loss')} TP={rec.get('take_profit')}")
        if notification_service:
            await notification_service.send_strategy_recommendation(rec, platform_metrics)
        if persistence:
            persistence.save_recommendation(rec, platform_metrics)
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
                 
                 # 推送巨鲸通知
                 if notification_service:
                     await notification_service.send_whale_alert(w, symbol, name)


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

    # Coin Discovery - OKX Only
    target_symbols = [Config.SYMBOL]
    if Config.ENABLE_MULTI_SYMBOL:
        market_label = "现货" if Config.MARKET_TYPE == 'spot' else "合约"
        logger.info(f"正在扫描 Binance 平台所有 USDT {market_label}交易对...")
        try:
            # Initialize Binance temporarily just for symbol discovery
            binance_temp = BinanceConnector()
            await binance_temp.initialize()
            await binance_temp.exchange.load_markets()
            tickers = await binance_temp.exchange.fetch_tickers()
            b_symbols = []
            for s, t in tickers.items():
                if '/USDT' not in s:
                    continue
                qv = t.get('quoteVolume')
                if qv is None:
                    base_vol = t.get('baseVolume')
                    last = t.get('last') or 0
                    qv = (base_vol or 0) * last
                if qv and qv >= Config.MIN_24H_QUOTE_VOLUME:
                    b_symbols.append(s)
            
            await binance_temp.close()
            
            if b_symbols:
                # Sort alphabetically
                target_symbols = sorted(b_symbols)
                logger.info(f"✅ Binance 高成交额监控列表 ({len(target_symbols)} 个币种)")
                # Log first 10 for preview
                logger.info(f"   示例: {', '.join(target_symbols[:10])}...")
            else:
                logger.warning("❌ 未在 Binance 发现满足成交额阈值的 USDT 交易对，回退到默认币种。")
        except Exception as e:
            logger.error(f"Binance 币种扫描失败: {e}")
            logger.warning("回退到默认币种。")

    taker_analyzer = TakerFlowAnalyzer(window=50)
    vol_spike_analyzer = VolumeSpikeAnalyzer()
    early_pump_analyzer = EarlyPumpAnalyzer()
    panic_dump_analyzer = PanicDumpAnalyzer()
    steady_growth_analyzer = SteadyGrowthAnalyzer()
    multi_analyzer = MultiPlatformAnalyzer()
    sf_analyzer = SpotFuturesAnalyzer()  # Spot-Futures correlation analyzer
    whale_watcher = WhaleWatcher(threshold=Config.WHALE_THRESHOLD) # $200k

    strategy = EntryExitStrategy()
    persistence = Persistence(Config.PERSIST_DB_PATH) if Config.ENABLE_PERSISTENCE else None
    
    # 初始化通知服务
    notification_service = None
    if Config.ENABLE_DINGTALK or Config.ENABLE_WECHAT:
        notification_service = NotificationService()
        logger.info("✅ 通知服务已启用")
        if Config.ENABLE_DINGTALK:
            logger.info(f"  - 钉钉推送: 已启用")
        if Config.ENABLE_WECHAT:
            logger.info(f"  - 企业微信推送: 已启用")
    else:
        logger.info("ℹ️  通知服务未启用（可在 .env 中配置）")
    
    # 启动实时 WebSocket 监控（后台任务）
    realtime_task = None
    if Config.ENABLE_REALTIME_MONITOR:
        logger.info("🚀 启动实时 WebSocket 监控...")
        realtime_monitor = RealtimeMonitor(notification_service=notification_service)
        realtime_task = asyncio.create_task(realtime_monitor.start())
        logger.info("✅ 实时监控已在后台运行")

    # 排除配置的品种
    target_symbols = [s for s in target_symbols if s not in Config.EXCLUDED_SYMBOLS]
    
    try:
        while True:
            cycle_start = time.time()
            logger.info(f"=== 开始新一轮扫描 ({len(target_symbols)} 币种) ===")
            
            # Process symbols in chunks of 5 to control concurrency
            for i in range(0, len(target_symbols), 5):
                chunk = target_symbols[i:i+5]
                tasks = [process_symbol(sym, initialized, taker_analyzer, multi_analyzer, whale_watcher, vol_spike_analyzer, early_pump_analyzer, panic_dump_analyzer, steady_growth_analyzer, sf_analyzer, strategy, notification_service, persistence) for sym in chunk]
                await asyncio.gather(*tasks)

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
