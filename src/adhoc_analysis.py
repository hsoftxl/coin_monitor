
import asyncio
import pandas as pd
from typing import Dict, List
from loguru import logger
import sys

# Add project root to path
sys.path.append(".")

from src.config import Config
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OKXConnector
from src.connectors.bybit import BybitConnector
from src.connectors.coinbase import CoinbaseConnector
from src.processors.data_processor import DataProcessor
from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.whale_watcher import WhaleWatcher
from src.services.notification import NotificationService
from src.strategies.entry_exit import EntryExitStrategy

# Disable default logger for clean output
logger.remove()
logger.add(sys.stderr, level="ERROR")

async def analyze_market():
    print("🚀 正在初始化市场分析 (GME-FFMS Core)...")
    
    # Target Symbols
    target_symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", 
        "DOGE/USDT", "ADA/USDT", "BNB/USDT", "LINK/USDT",
        "SUI/USDT", "PEPE/USDT"
    ]
    
    connectors = {
        'binance': BinanceConnector(),
        'okx': OKXConnector(),
        'bybit': BybitConnector(),
        'coinbase': CoinbaseConnector()
    }
    
    # Initialize
    active_connectors = {}
    print("🔌 连接交易所 API...")
    for name, conn in connectors.items():
        try:
            await conn.initialize()
            active_connectors[name] = conn
        except Exception as e:
            print(f"⚠️ {name} 连接失败: {e}")
            
    if not active_connectors:
        print("❌ 无可用连接器")
        return

    taker_analyzer = TakerFlowAnalyzer(window=50)
    multi_analyzer = MultiPlatformAnalyzer()
    notification_service = NotificationService() if (Config.ENABLE_DINGTALK or Config.ENABLE_WECHAT) else None
    strategy = EntryExitStrategy() if Config.ENABLE_STRATEGY else None
    
    reports = []
    
    print(f"📊 正在分析 {len(target_symbols)} 个主流币种 (需约 10-20 秒)...")
    print("-" * 60)

    for symbol in target_symbols:
        # Check support
        supported_conns = {}
        for name, conn in active_connectors.items():
            if symbol in conn.exchange.symbols:
                supported_conns[name] = conn
        
        if len(supported_conns) < 2:
            continue
            
        # Fetch Data
        tasks = {
            name: conn.fetch_standard_candles(symbol=symbol, limit=100)
            for name, conn in supported_conns.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        platform_metrics = {}
        valid_count = 0
        
        for i, (name, _) in enumerate(tasks.items()):
            res = results[i]
            if isinstance(res, list) and len(res) >= 50:
                df = DataProcessor.process_candles(res)
                metrics = taker_analyzer.analyze(df)
                platform_metrics[name] = metrics
                valid_count += 1
        
        if valid_count < 2:
            continue
            
        # Consensus
        consensus = multi_analyzer.get_market_consensus(platform_metrics)
        signals = multi_analyzer.analyze_signals(platform_metrics, symbol)
        if strategy:
            rec = strategy.evaluate(platform_metrics, consensus, signals, symbol)
            if rec.get('action') and notification_service:
                await notification_service.send_strategy_recommendation(rec, platform_metrics)
        
        # Calculate Total Flow
        total_flow = sum(m['cumulative_net_flow'] for m in platform_metrics.values())
        
        reports.append({
            "symbol": symbol,
            "consensus": consensus,
            "total_flow": total_flow,
            "signals": signals,
            "metrics": platform_metrics
        })

    # Close connectors
    for conn in active_connectors.values():
        await conn.close()
        
    # --- Generate Advice Report ---
    print("\n" + "="*30 + " 交易建议报告 " + "="*30)
    print(f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Sort by Flow Magnitude (Hot/Cold)
    reports.sort(key=lambda x: x['total_flow'], reverse=True)
    
    for r in reports:
        symbol = r['symbol']
        cons = r['consensus']
        flow = r['total_flow']
        signals = r['signals']
        
        # Determine Verdict
        verdict = "观望"
        action_color = ""
        reason = ""
        entry_sugg = ""
        exit_sugg = ""
        
        # Logic for Advice
        if "强力看涨" in cons or any(s['grade'] == 'A+' for s in signals):
            verdict = "🟢 强烈买入 (Strong Buy)"
            reason = "主力全平台吸筹，市场共识一致看涨。"
            entry_sugg = "现价进场，或等待微幅回调。"
            exit_sugg = "跌破关键支撑或共识转弱时离场。"
        elif "倾向看涨" in cons:
            verdict = "🟡 谨慎看涨 (Weak Buy)"
            reason = "资金整体流入，但存在分歧，需关注后续动能。"
            entry_sugg = "等待突破确认或回调企稳。"
            exit_sugg = "跌破短期均线离场。"
        elif "强力看跌" in cons:
            verdict = "🔴 强烈卖出 (Strong Sell)"
            reason = "主力全平台出货，市场共识一致看跌。"
            entry_sugg = "做空或做多回避。"
            exit_sugg = "已有持仓建议止损或减仓。"
        elif "倾向看跌" in cons:
            verdict = "🟠 谨慎看跌 (Weak Sell)"
            reason = "资金整体流出，抛压较重。"
            entry_sugg = "不建议做多，可尝试高空。"
            exit_sugg = "反弹无力时离场。"
        else:
            verdict = "⚪ 震荡观望 (Neutral)"
            reason = "多空力量平衡，方向不明。"
            entry_sugg = "暂不操作，等待方向选择。"
            exit_sugg = "区间操作，或观望。"

        # Special Signal Override
        special_note = ""
        for s in signals:
            special_note += f"\n   🔥 **信号触发**: {s['type']} ({s['desc']})"

        # Formatting Output
        flow_str = f"+${flow/1000:.0f}k" if flow > 0 else f"-${abs(flow)/1000:.0f}k"
        
        print(f"🪙 **{symbol}**")
        print(f"   📊 资金流向: {flow_str} | 共识: {cons}")
        print(f"   💡 建议: {verdict}")
        if special_note:
            print(f"   {special_note}")
        print(f"   📝 理由: {reason}")
        if "观望" not in verdict:
            print(f"   🎯 开仓: {entry_sugg}")
            print(f"   🛑 平仓: {exit_sugg}")
        print("-" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(analyze_market())
    except KeyboardInterrupt:
        pass
