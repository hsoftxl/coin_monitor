import asyncio
import time
from typing import Dict, List, Optional
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
from src.services.funding_rate_monitor import FundingRateMonitor
from src.strategies.entry_exit import EntryExitStrategy
from src.analyzers.steady_growth import SteadyGrowthAnalyzer
from src.storage.persistence import Persistence
from src.utils.market_regime import MarketRegimeDetector
from src.core.context import AnalysisContext
from src.core.symbol_processor import (
    fetch_symbol_data,
    analyze_platform,
    aggregate_signals,
    generate_recommendations
)
from src.core.exceptions import ExchangeConnectionError, DataFetchError

async def process_symbol(symbol: str, ctx: AnalysisContext) -> None:
    """
    Process a single symbol across all exchanges.
    
    使用模块化函数重构，提高代码可维护性。
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC/USDT')
        ctx: AnalysisContext containing all analyzers and services
    """
    # 1. Fetch all data
    data = await fetch_symbol_data(symbol, ctx)
    valid_connectors = data['valid_connectors']
    
    if not valid_connectors:
        return
    
    candle_results = data['candle_results']
    ticker_24h_vol = data['ticker_24h_vol']
    df_res = data['df_res']
    trade_results = data['trade_results']
    spot_df = data['spot_df']
    futures_df = data['futures_df']
    
    # Spot-Futures Correlation Analysis
    sf_correlation = None
    if Config.ENABLE_SPOT_FUTURES_CORRELATION and spot_df is not None and futures_df is not None:
        sf_correlation = ctx.sf_analyzer.analyze_correlation(spot_df, futures_df, symbol)
    
    # 2. Analyze Individual Platforms
    platform_metrics: Dict[str, Dict[str, Any]] = {}
    valid_data_count = 0
    main_df = None
    volatility_level = 'NORMAL'
    
    # Create tasks dict for iteration
    tasks_dict = dict(zip(valid_connectors.keys(), candle_results))
    
    for i, (name, res) in enumerate(tasks_dict.items()):
        if isinstance(res, Exception) or not res or len(res) < 5:
            continue
        
        valid_data_count += 1
        trade_result = trade_results[i] if i < len(trade_results) else None
        
        # Analyze platform
        analysis_result = await analyze_platform(
            symbol=symbol,
            platform_name=name,
            candle_result=res,
            trade_result=trade_result,
            ticker_24h_vol=ticker_24h_vol,
            df_res=df_res,
            sf_correlation=sf_correlation,
            ctx=ctx
        )
        
        if analysis_result['metrics']:
            platform_metrics[name] = analysis_result['metrics']
            if analysis_result.get('df') is not None:
                main_df = analysis_result['df']
        
        # Extract volatility level from signals
        for signal_type, signal_data in analysis_result.get('signals', []):
            if signal_type in ('early_pump', 'panic_dump') and 'volatility_level' in signal_data:
                volatility_level = signal_data['volatility_level']
                break
        
    if valid_data_count < 2:
        return
    
    # 3. Aggregate signals and consensus
    aggregation_result = await aggregate_signals(
        symbol=symbol,
        platform_metrics=platform_metrics,
        df=main_df,
        df_res=df_res,
        ctx=ctx
    )
    
    consensus = aggregation_result['consensus']
    signals = aggregation_result['signals']
    
    # Process signals
    for signal in signals:
        logger.critical(f"🚨 [{symbol}] 信号触发 [{signal['grade']}]: {signal['type']} - {signal['desc']}")
        if ctx.notification_service:
            await ctx.notification_service.dispatch_signal(signal, platform_metrics, symbol)
        if ctx.persistence:
            ctx.persistence.save_signal(signal, platform_metrics, symbol)
    
    # 4. Generate recommendations
    await generate_recommendations(
        symbol=symbol,
        consensus=consensus,
        signals=signals,
        platform_metrics=platform_metrics,
        df=main_df,
        df_res=df_res,
        volatility_level=volatility_level,
        ctx=ctx
    )
    
    # 5. Whale Watcher (separate loop for all trades)
    for i, (name, _) in enumerate(valid_connectors.items()):
        if i < len(trade_results):
            t_res = trade_results[i]
            if isinstance(t_res, list) and t_res:
                whales = ctx.whale_watcher.check_trades(t_res)
                for w in whales:
                    side = w['side'].upper()
                    side_cn = "买入" if side == 'BUY' else "卖出"
                    color = "green" if side == 'BUY' else "red"
                    logger.warning(f"🐳 [{symbol}] 巨鲸监测 [{name.upper()}]: <{color}>{side_cn} ${w['cost']:,.0f}</{color}> @ {w['price']}")
                    
                    # 推送巨鲸通知
                    if ctx.notification_service:
                        await ctx.notification_service.send_whale_alert(w, symbol, name)


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
    
    market_regime_detector = MarketRegimeDetector() # P1/P2 新增

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
    realtime_monitor = None
    if Config.ENABLE_REALTIME_MONITOR:
        logger.info("🚀 启动实时 WebSocket 监控...")
        realtime_monitor = RealtimeMonitor(notification_service=notification_service, strategy=strategy)
        realtime_task = asyncio.create_task(realtime_monitor.start())
        logger.info("✅ 实时监控已在后台运行")
    
    # 启动资金费率监控器（后台任务）
    funding_task = None
    funding_monitor = None
    if Config.ENABLE_FUNDING_RATE_MONITOR:
        logger.info("🚀 启动资金费率监控器...")
        funding_monitor = FundingRateMonitor()
        funding_task = asyncio.create_task(funding_monitor.run())
        logger.info("✅ 资金费率监控已在后台运行")

    # 排除配置的品种
    target_symbols = [s for s in target_symbols if s not in Config.EXCLUDED_SYMBOLS]
    
    try:
        while True:
            cycle_start = time.time()
            logger.info(f"=== 开始新一轮扫描 ({len(target_symbols)} 币种) ===")
            
            # P1: 获取市场环境 (Based on BTC) - 使用缓存机制
            market_regime = 'NEUTRAL'
            # 先检查缓存
            cached_result = market_regime_detector.get_cached_result()
            if cached_result:
                market_regime = cached_result['regime']
                logger.debug(f"📊 使用缓存的市场环境: {cached_result['desc']}")
            else:
                # 缓存过期，需要重新获取数据
                try:
                    # 优先使用 Binance
                    regime_conn = initialized.get('binance') or list(initialized.values())[0]
                    if regime_conn:
                        btc_candles = await regime_conn.fetch_standard_candles('BTC/USDT', limit=100)
                        if btc_candles:
                            btc_df = DataProcessor.process_candles(btc_candles)
                            regime_info = market_regime_detector.analyze(btc_df)
                            market_regime = regime_info['regime']
                            logger.info(f"📊 全局市场环境: {regime_info['desc']}")
                except Exception as e:
                    logger.warning(f"无法获取市场环境数据: {e}")
                    # 如果获取失败，尝试使用过期缓存
                    if market_regime_detector._cache:
                        market_regime = market_regime_detector._cache['regime']
                        logger.warning(f"使用过期缓存的市场环境: {market_regime_detector._cache['desc']}")
            
            # Create analysis context
            ctx = AnalysisContext(
                connectors=initialized,
                taker_analyzer=taker_analyzer,
                multi_analyzer=multi_analyzer,
                whale_watcher=whale_watcher,
                vol_spike_analyzer=vol_spike_analyzer,
                early_pump_analyzer=early_pump_analyzer,
                panic_dump_analyzer=panic_dump_analyzer,
                steady_growth_analyzer=steady_growth_analyzer,
                sf_analyzer=sf_analyzer,
                strategy=strategy,
                notification_service=notification_service,
                persistence=persistence,
                market_regime=market_regime
            )
            
            # Process symbols in smaller chunks to reduce API load
            chunk_size = 2  # 进一步减少每次处理的符号数量
            for i in range(0, len(target_symbols), chunk_size):
                chunk = target_symbols[i:i+chunk_size]
                tasks = [process_symbol(sym, ctx) for sym in chunk]
                await asyncio.gather(*tasks)

                # Increased sleep between chunks to reduce API requests
                await asyncio.sleep(Config.RATE_LIMIT_DELAY * 2)

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
        
        # 取消实时监控任务
        if realtime_task:
            realtime_task.cancel()
            try:
                await realtime_task
            except asyncio.CancelledError:
                logger.info("实时监控任务已取消")
            except Exception as e:
                logger.error(f"取消实时监控任务时出错: {e}")
        
        # 取消资金费率监控任务
        if funding_task:
            funding_task.cancel()
            try:
                await funding_task
            except asyncio.CancelledError:
                logger.info("资金费率监控任务已取消")
            except Exception as e:
                logger.error(f"取消资金费率监控任务时出错: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
