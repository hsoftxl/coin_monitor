#!/usr/bin/env python3
"""
独立的策略学习程序
持续运行，自动学习最优交易策略，实时监测高胜率交易机会并通知
"""

import sys
import os
import argparse
import json
import asyncio
from datetime import datetime
from loguru import logger

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.strategy_learner import StrategyLearner
from services.symbol_selector import SymbolSelector
from services.notification import NotificationService
from strategies.entry_exit import EntryExitStrategy
from connectors.binance import BinanceConnector


async def send_trading_signal_notification(
    notification_service: NotificationService,
    symbols: list,
    strategy_params: dict,
    reason: str = "策略筛选"
):
    """发送交易信号通知（使用主通道）"""
    
    if not isinstance(symbols, list) or not symbols:
        return
    
    if not isinstance(strategy_params, dict):
        strategy_params = {}
    
    # 检查通知服务是否启用
    if not notification_service:
        return
    
    # 格式化币种列表
    symbols_text = "\n".join([f"- **{sym.replace('/USDT', '')}**" for sym in symbols])
    
    params_text = f"""
- 最小资金流向: {strategy_params.get('min_total_flow', 100000):,.0f}
- 最小买卖比: {strategy_params.get('min_ratio', 1.5):.1f}
- 止损倍数: {strategy_params.get('atr_sl_mult', 1.5):.1f}
- 止盈倍数: {strategy_params.get('atr_tp_mult', 2.0):.1f}"""

    # 生成币种的币安地址列表（根据市场类型）
    symbols_with_url = []
    for sym in symbols:
        binance_url = notification_service._get_binance_url(sym, lang="en")
        symbols_with_url.append(f"- **[{sym}]({binance_url})**")
    symbols_text = "\n".join(symbols_with_url)
    
    message = f"""### 🚀 【实盘交易信号】{reason}

**通知时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**发现数量**: {len(symbols)} 个符合条件的品种

**策略参数**:{params_text}

---

### ✅ 符合策略条件的品种:

{symbols_text}

---

<font color='comment'>*自动策略监测系统 - 请结合K线形态和风险管理谨慎决策*</font>
"""
    
    logger.info(f"📢 发送交易信号通知 ({len(symbols)} 个品种)...")
    
    # 交易信号使用主通道
    if notification_service.enable_dingtalk:
        await notification_service.send_dingtalk(message, at_all=False)
    
    if notification_service.enable_wechat:
        await notification_service.send_wechat(message)
    
    logger.info("✅ 交易信号通知发送完成")


async def send_strategy_learning_notification(
    notification_service: NotificationService,
    best_params: dict,
    winrate: float,
    cycle_num: int
):
    """发送策略学习通知（使用独立通道）"""
    
    # 检查通知服务是否启用
    if not notification_service:
        return
    
    params_text = ""
    for key, value in best_params.items():
        params_text += f"- **{key}**: {value}\n"
    
    message = f"""### 📊 【策略学习】第 {cycle_num} 轮优化完成

**学习时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**全局最优胜率**: <font color='green'>**{winrate:.2%}**</font>

**最优参数**:
{params_text}

---

<font color='comment'>*自动策略学习系统 - 轮次 {cycle_num}*</font>
"""
    
    logger.info("📢 发送策略学习通知...")
    
    # 策略学习通知使用主通道发送
    if notification_service.enable_dingtalk:
        await notification_service.send_dingtalk(message, at_all=False)
    if notification_service.enable_wechat:
        await notification_service.send_wechat(message)
    logger.info("✅ 策略学习通知已通过主通道发送")
    
    logger.info("✅ 策略学习通知处理完成")


async def get_top_volume_symbols(binance, limit: int = 100) -> list:
    """获取高成交量品种列表"""
    max_retries = 3
    retry_delay = 2  # 秒
    
    for attempt in range(max_retries):
        try:
            tickers = await binance.exchange.fetch_tickers()
            
            usdt_tickers = {}
            for s, t in tickers.items():
                if '/USDT' in s:
                    qv = t.get('quoteVolume')
                    if qv is None:
                        base_vol = t.get('baseVolume')
                        last = t.get('last') or 0
                        qv = (base_vol or 0) * last
                    if qv and qv >= Config.MIN_24H_QUOTE_VOLUME:
                        usdt_tickers[s] = qv
            
            sorted_symbols = sorted(usdt_tickers.items(), key=lambda x: x[1], reverse=True)
            return [s[0] for s in sorted_symbols[:limit]]
        except Exception as e:
            logger.error(f"❌ 第 {attempt+1}/{max_retries} 次获取高成交量品种失败: {e}")
            if attempt < max_retries - 1:
                logger.info(f"⏱️  {retry_delay}秒后重试...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
            else:
                logger.error("❌ 获取高成交量品种失败，返回空列表")
                return []


async def scan_and_notify(
    binance: BinanceConnector,
    notification_service,
    strategy: EntryExitStrategy,
    all_symbols: list,
    last_notified: set
) -> set:
    """扫描品种，发现新机会时通知"""
    
    if not strategy:
        return last_notified
    
    try:
        selector = SymbolSelector(strategy)
        selected_symbols = await selector.select_symbols(all_symbols)
        
        # 找出新增的品种
        new_symbols = [s for s in selected_symbols if s not in last_notified]
        
        if new_symbols:
            logger.info(f"🎯 发现 {len(new_symbols)} 个新品种符合条件")
            await send_trading_signal_notification(
                notification_service,
                new_symbols,
                {
                    'min_total_flow': strategy.min_total_flow,
                    'min_ratio': strategy.min_ratio,
                    'atr_sl_mult': strategy.atr_sl_mult,
                    'atr_tp_mult': strategy.atr_tp_mult
                },
                "实时监测到新机会"
            )
        
        # 更新已通知的品种集合
        return set(selected_symbols)
    except Exception as e:
        logger.error(f"❌ 扫描品种失败: {e}")
        import traceback
        traceback.print_exc()
        # 返回原有的已通知集合，避免丢失状态
        return last_notified


async def run_learning_cycle(cycle_num: int, args, notification_service, binance) -> tuple:
    """执行一轮策略学习，返回(学习是否成功, 最优策略, 胜率)"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🔄 第 {cycle_num} 轮策略学习")
    logger.info(f"{'='*60}")
    
    try:
        # 1. 获取高成交量品种
        top_symbols = await get_top_volume_symbols(binance, args.limit)
        if not top_symbols:
            logger.warning("⚠️  未获取到高成交量品种，跳过本轮学习")
            return False, None, 0.0
        
        # 2. 策略学习
        logger.info("🔍 开始策略学习...")
        learner = StrategyLearner()
        results = await learner.learn(symbols=top_symbols, days=args.days)
        
        if results and 'global' in results:
            best_params = results['global']['params']
            winrate = results['global']['winrate']
            learned_symbols = results['global']['symbols']
            
            logger.info(f"🎉 策略学习完成！")
            logger.info(f"   全局最优胜率: {winrate:.2%}")
            logger.info(f"   最优参数: {best_params}")
            
            # 创建最优策略
            best_strategy = EntryExitStrategy(**best_params)
            best_strategy.is_strategy_learned = True
            
            # 保存结果
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump({
                    'best_params': best_params,
                    'winrate': winrate,
                    'learned_symbols': learned_symbols,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'cycle': cycle_num
                }, f, indent=2, ensure_ascii=False)
            
            return True, best_strategy, winrate
        else:
            logger.warning("⚠️  策略学习失败")
            return False, None, 0.0
        
    except Exception as e:
        logger.error(f"❌ 第 {cycle_num} 轮学习失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None, 0.0


async def main():
    """主函数 - 持续运行策略学习和实时监测"""
    parser = argparse.ArgumentParser(description='独立策略学习程序（持续运行版）')
    parser.add_argument('--days', type=int, default=Config.STRATEGY_LEARNING_DAYS,
                        help='回测天数 (默认: %(default)s)')
    parser.add_argument('--limit', type=int, default=100,
                        help='回测品种数量限制 (默认: %(default)s)')
    parser.add_argument('--learn-interval', type=int, default=14400,
                        help='策略学习间隔，单位秒 (默认: 14400，即4小时)')
    parser.add_argument('--scan-interval', type=int, default=300,
                        help='品种扫描间隔，单位秒 (默认: 300，即5分钟)')
    parser.add_argument('--output', type=str, default='strategy_results.json',
                        help='策略结果输出文件 (默认: %(default)s)')
    parser.add_argument('--notify', action='store_true', default=True,
                        help='发现机会时发送通知 (默认: 启用)')
    parser.add_argument('--no-notify', action='store_false', dest='notify',
                        help='不发送通知')
    args = parser.parse_args()
    
    learn_interval_text = f"{args.learn_interval // 3600}小时" if args.learn_interval >= 3600 else f"{args.learn_interval // 60}分钟"
    scan_interval_text = f"{args.scan_interval // 60}分钟" if args.scan_interval >= 60 else f"{args.scan_interval}秒"
    
    logger.info("🚀 启动自动策略交易系统...")
    logger.info(f"📊 回测天数: {args.days}天, 品种限制: {args.limit}")
    logger.info(f"🔄 学习间隔: {learn_interval_text}")
    logger.info(f"🔍 扫描间隔: {scan_interval_text}")
    logger.info(f"🔔 通知: {'是' if args.notify else '否'}")
    logger.info(f"📁 拉盘通道: {'启用' if Config.ENABLE_PUMP_CHANNEL else '未启用'}")
    logger.info(f"📁 稳步上涨通道: {'启用' if Config.ENABLE_GROWTH_CHANNEL else '未启用'}")
    
    notification_service = None
    if args.notify and (Config.ENABLE_DINGTALK or Config.ENABLE_WECHAT):
        notification_service = NotificationService()
        logger.info("✅ 通知服务已启用")
    else:
        logger.info("ℹ️  通知服务未启用")
    
    binance = None
    current_strategy = None
    current_winrate = 0.0
    cycle_num = 0
    last_notified = set()
    all_symbols = []
    
    try:
        # 初始化binance连接器，添加重试机制
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                binance = BinanceConnector()
                await binance.initialize()
                await binance.exchange.load_markets()
                logger.info("✅ 成功初始化Binance连接器")
                break
            except Exception as e:
                logger.error(f"❌ 第 {attempt+1}/{max_retries} 次初始化Binance连接器失败: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏱️  {retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error("❌ Binance连接器初始化失败，程序退出")
                    return
        
        # 初始获取品种列表
        all_symbols = await get_top_volume_symbols(binance, args.limit)
        if not all_symbols:
            logger.warning("⚠️  未获取到品种列表，使用默认品种")
            all_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
        
        # 立即执行第一轮学习
        cycle_num = 1
        success, current_strategy, current_winrate = await run_learning_cycle(cycle_num, args, notification_service, binance)
        if success and current_strategy:
            # 学习完成后立即扫描
            last_notified = await scan_and_notify(
                binance, notification_service, current_strategy, all_symbols, last_notified
            )
        
        # 主循环
        last_learn_time = datetime.now()
        last_symbol_update_time = datetime.now()
        symbol_update_interval = 3600  # 每小时更新一次品种列表
        
        while True:
            await asyncio.sleep(args.scan_interval)
            
            try:
                # 检查是否需要更新品种列表
                time_since_symbol_update = (datetime.now() - last_symbol_update_time).total_seconds()
                if time_since_symbol_update >= symbol_update_interval:
                    logger.info("🔄 更新高成交量品种列表...")
                    new_symbols = await get_top_volume_symbols(binance, args.limit)
                    if new_symbols:
                        all_symbols = new_symbols
                        last_symbol_update_time = datetime.now()
                        logger.info(f"✅ 更新完成，共 {len(all_symbols)} 个品种")
                    else:
                        logger.warning("⚠️  更新品种列表失败，继续使用旧列表")
                
                # 检查是否需要重新学习策略
                time_since_learn = (datetime.now() - last_learn_time).total_seconds()
                need_relearn = time_since_learn >= args.learn_interval
                
                if need_relearn:
                    cycle_num += 1
                    success, current_strategy, current_winrate = await run_learning_cycle(
                        cycle_num, args, notification_service, binance
                    )
                    if success:
                        last_learn_time = datetime.now()
                        last_notified = set()  # 重置已通知集合
                        # 学习完成后立即扫描最新品种
                        if current_strategy:
                            last_notified = await scan_and_notify(
                                binance, notification_service, current_strategy, all_symbols, last_notified
                            )
                    else:
                        logger.warning("学习失败，继续使用上次策略")
                
                # 持续扫描品种
                if current_strategy:
                    last_notified = await scan_and_notify(
                        binance, notification_service, current_strategy, all_symbols, last_notified
                    )
            except Exception as e:
                logger.error(f"❌ 主循环执行失败: {e}")
                import traceback
                traceback.print_exc()
                # 继续循环，不退出程序
                logger.info("🔄 继续主循环")
    
    except KeyboardInterrupt:
        logger.info("\n⏹️  用户中断程序，正在停止...")
    except Exception as e:
        logger.error(f"❌ 程序执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if binance:
            await binance.close()
        logger.info("👋 程序已退出")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
