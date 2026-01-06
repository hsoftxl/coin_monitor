"""
Symbol Processing Module
将 process_symbol 函数拆分为多个小函数，提高可维护性
"""

import asyncio
from typing import Dict, List, Optional, Any
import pandas as pd
from loguru import logger

from src.config import Config
from src.processors.data_processor import DataProcessor
from src.core.context import AnalysisContext
from src.core.exceptions import DataFetchError, AnalysisError


async def fetch_symbol_data(
    symbol: str, 
    ctx: AnalysisContext
) -> Dict[str, Any]:
    """
    获取币种的所有数据（K线、交易记录、Ticker等）
    
    Args:
        symbol: 交易对符号
        ctx: 分析上下文
        
    Returns:
        包含所有数据的字典:
        {
            'valid_connectors': Dict[str, ExchangeConnector],
            'candle_results': List,
            'ticker_24h_vol': float,
            'df_res': Optional[pd.DataFrame],
            'trade_results': List,
            'spot_df': Optional[pd.DataFrame],
            'futures_df': Optional[pd.DataFrame]
        }
    """
    # 0. Pre-filter: Check which exchanges support this symbol
    valid_connectors = {}
    for name, conn in ctx.connectors.items():
        try:
            if not (conn.exchange and conn.exchange.markets):
                continue
            if symbol in conn.exchange.symbols:
                valid_connectors[name] = conn
            elif name == 'coinbase':
                usd_symbol = symbol.replace('/USDT', '/USD')
                if usd_symbol in conn.exchange.symbols:
                    valid_connectors[name] = conn
        except (AttributeError, KeyError, TypeError):
            # Exchange not initialized or symbol not available
            pass
    
    if not valid_connectors:
        return {'valid_connectors': {}}
    
    # 1. Fetch 1m Candles (main data)
    # 为避免API限流，使用顺序获取而不是并行获取
    results = []
    for name, conn in valid_connectors.items():
        try:
            candles = await conn.fetch_standard_candles(symbol=symbol, limit=Config.LIMIT_KLINE)
            results.append(candles)
        except Exception as e:
            results.append(e)
        
        # 添加请求间隔控制，避免短时间内发送过多请求
        if name != list(valid_connectors.keys())[-1]:
            await asyncio.sleep(Config.RATE_LIMIT_DELAY)
    
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
        except (AttributeError, KeyError, TypeError):
             pass

    # Fetch Multi-Timeframe Data (for Resonance)
    df_res = None
    if Config.ENABLE_MULTI_TIMEFRAME and valid_connectors:
        first_conn = list(valid_connectors.values())[0]
        try:
            # fetch_candles_timeframe returns raw OHLCV data, need to convert to StandardCandle first
            raw_data = await first_conn.fetch_candles_timeframe(symbol, Config.MTF_RES_TIMEFRAME, limit=100)
            if raw_data:
                # Convert raw OHLCV to StandardCandle format
                # Raw format: [timestamp, open, high, low, close, volume]
                from src.models import StandardCandle
                standard_candles = []
                for k in raw_data:
                    if len(k) >= 6:
                        standard_candles.append(StandardCandle(
                            timestamp=int(k[0]),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]),
                            taker_buy_volume=None,  # Not available in basic OHLCV
                            taker_sell_volume=None,
                            quote_volume=None,
                            volume_type='base',
                            exchange_id=first_conn.exchange_id
                        ))
                if standard_candles:
                    df_res = DataProcessor.process_candles(standard_candles)
        except (DataFetchError, KeyError, ValueError, TypeError, IndexError) as e:
            logger.debug(f"[{symbol}] 共振数据({Config.MTF_RES_TIMEFRAME})获取失败: {e}")
    
    # Fetch Spot-Futures Data (for correlation analysis)
    spot_df = None
    futures_df = None
    if Config.ENABLE_SPOT_FUTURES_CORRELATION and 'binance' in valid_connectors:
        try:
            # Placeholder for future implementation
            pass
        except Exception:
            pass
    
    # Fetch Trades (Best effort for Whale Watcher)
    trade_tasks = {
         name: conn.fetch_trades(symbol=symbol, limit=100)
         for name, conn in valid_connectors.items()
    }
    trade_results = await asyncio.gather(*trade_tasks.values(), return_exceptions=True)
    
    # Create a mapping of platform names to their results for easier access
    # Note: results and trade_results are lists, we need to map them back to platform names
    return {
        'valid_connectors': valid_connectors,
        'candle_results': list(results),  # Convert to list for easier indexing
        'ticker_24h_vol': ticker_24h_vol,
        'df_res': df_res,
        'trade_results': list(trade_results),  # Convert to list for easier indexing
        'spot_df': spot_df,
        'futures_df': futures_df,
        'tasks_dict': dict(zip(valid_connectors.keys(), results))  # For easier iteration
    }


async def analyze_platform(
    symbol: str,
    platform_name: str,
    candle_result: Any,
    trade_result: Any,
    ticker_24h_vol: float,
    df_res: Optional[pd.DataFrame],
    sf_correlation: Optional[Dict],
    ctx: AnalysisContext
) -> Dict[str, Any]:
    """
    分析单个平台的数据
    
    Args:
        symbol: 交易对符号
        platform_name: 平台名称
        candle_result: K线数据结果
        trade_result: 交易记录结果
        ticker_24h_vol: 24小时成交额
        df_res: 共振时间框架数据
        sf_correlation: 现货-合约相关性分析结果
        ctx: 分析上下文
        
    Returns:
        包含平台指标和分析结果的字典
    """
    if isinstance(candle_result, Exception) or not candle_result or len(candle_result) < 5:
        return {'metrics': None, 'signals': []}
    
    # Standardize & Flow
    df = DataProcessor.process_candles(candle_result)
    metrics = ctx.taker_analyzer.analyze(df)
    
    signals = []
    
    # Volume Spike Analysis
    spike = ctx.vol_spike_analyzer.analyze(df, symbol)
    if spike:
         spike['vol_24h'] = ticker_24h_vol
         logger.warning(f"🔥 [{symbol}] 成交量暴增: {spike['ratio']:.1f}x (涨幅 {spike['price_change']:.2f}%)")
         if ctx.notification_service:
             await ctx.notification_service.send_volume_spike_alert(spike, symbol)
         signals.append(('volume_spike', spike))
             
    # Whale Analysis (for Confirmation)
    current_whales = []
    if isinstance(trade_result, list) and trade_result:
        current_whales = ctx.whale_watcher.check_trades(trade_result)

    # Early Pump Analysis
    sf_strength = sf_correlation['strength'] if sf_correlation else None
    pump = ctx.early_pump_analyzer.analyze(
        df, 
        symbol,
        df_res=df_res,
        sf_strength=sf_strength,
        whales=current_whales
    )
    if pump:
         pump['vol_24h'] = ticker_24h_vol
         logger.critical(f"[{symbol}] {pump['desc']}")
         if ctx.notification_service:
             await ctx.notification_service.send_early_pump_alert(pump, symbol)
         signals.append(('early_pump', pump))

    # Panic Dump Analysis
    allow_short = True
    if Config.SHORT_ONLY_IN_BEAR and ctx.market_regime not in ['BEAR', 'NEUTRAL_BEAR']:
        allow_short = False
        
    dump = None
    if allow_short:
        dump = ctx.panic_dump_analyzer.analyze(
            df,
            symbol,
            df_res=df_res,
            sf_strength=sf_strength,
            whales=current_whales
        )
        
    if dump:
         dump['vol_24h'] = ticker_24h_vol
         logger.critical(f"📉 [{symbol}] {dump['desc']}")
         if ctx.notification_service:
             await ctx.notification_service.send_panic_dump_alert(dump, symbol)
         signals.append(('panic_dump', dump))

    # Steady Growth Analysis
    steady = ctx.steady_growth_analyzer.analyze(df_res, symbol)
    if steady:
         steady['vol_24h'] = ticker_24h_vol
         logger.info(f"💎 [{symbol}] {steady['desc']}")
         if ctx.notification_service:
             # 检查策略是否是学习后的
             is_strategy_learned = hasattr(ctx.strategy, 'is_strategy_learned') and ctx.strategy.is_strategy_learned
             await ctx.notification_service.send_steady_growth_alert(steady, symbol, is_strategy_learned=is_strategy_learned)
         signals.append(('steady_growth', steady))
    
    return {
        'metrics': metrics,
        'signals': signals,
        'df': df
    }


async def aggregate_signals(
    symbol: str,
    platform_metrics: Dict[str, Dict[str, Any]],
    df: Optional[pd.DataFrame],
    df_res: Optional[pd.DataFrame],
    ctx: AnalysisContext
) -> Dict[str, Any]:
    """
    聚合多平台信号和市场共识
    
    Args:
        symbol: 交易对符号
        platform_metrics: 各平台的指标
        df: 主时间框架数据
        df_res: 共振时间框架数据
        ctx: 分析上下文
        
    Returns:
        包含共识和信号的字典
    """
    if len(platform_metrics) < 2:
        return {'consensus': '数据不足', 'signals': []}
    
    # Consensus & Signals
    consensus = ctx.multi_analyzer.get_market_consensus(platform_metrics)
    
    # Log Output
    log_parts = []
    total_flow = 0
    for name, m in platform_metrics.items():
        flow = m.get('cumulative_net_flow', 0)
        total_flow += flow
        tag = "green" if flow > 0 else "red"
        short_name = name[:3].upper()
        log_parts.append(f"{short_name}:<{tag}>{flow/1000:.0f}k</{tag}>")
    
    # Determine consensus color
    cons_tag = "white"
    if "看涨" in consensus or "BULLISH" in consensus: cons_tag = "green"
    elif "看跌" in consensus or "BEARISH" in consensus: cons_tag = "red"
    
    logger.info(f"💰 <bold>{symbol.ljust(9)}</bold> | 共识: <{cons_tag}>{consensus.split('(')[0]}</{cons_tag}> | {' | '.join(log_parts)}")
    
    # 推送市场共识通知
    if ctx.notification_service:
        await ctx.notification_service.send_consensus_alert(consensus, platform_metrics, symbol)

    # Signals
    signals = ctx.multi_analyzer.analyze_signals(platform_metrics, symbol=symbol, df_5m=df, df_1h=df_res)
    
    return {
        'consensus': consensus,
        'signals': signals,
        'platform_metrics': platform_metrics
    }


async def generate_recommendations(
    symbol: str,
    consensus: str,
    signals: List[Dict[str, Any]],
    platform_metrics: Dict[str, Dict[str, Any]],
    df: Optional[pd.DataFrame],
    df_res: Optional[pd.DataFrame],
    volatility_level: str,
    ctx: AnalysisContext
) -> Optional[Dict[str, Any]]:
    """
    生成交易策略建议
    
    Args:
        symbol: 交易对符号
        consensus: 市场共识
        signals: 信号列表
        platform_metrics: 平台指标
        df: 主时间框架数据
        df_res: 共振时间框架数据
        volatility_level: 波动率等级
        ctx: 分析上下文
        
    Returns:
        策略建议字典，如果没有建议则返回 None
    """
    rec = ctx.strategy.evaluate(platform_metrics, consensus, signals, symbol, df_5m=df, df_1h=df_res)
    
    pos = ctx.strategy.compute_position(rec, volatility_level=volatility_level) if rec.get('action') else {}
    rec.update(pos)
    
    if rec.get('action') and rec.get('size_base'):
        logger.info(f"🎯 [{symbol}] 策略建议: {rec['action']} {rec['side']} @ {rec['price']:.4f} Size={rec.get('size_base'):.4f} ({rec.get('notional_usd'):.0f}U)")
        if ctx.notification_service:
            await ctx.notification_service.send_strategy_recommendation(rec, platform_metrics)
        if ctx.persistence:
            ctx.persistence.save_recommendation(rec, platform_metrics)
        return rec
    
    return None
