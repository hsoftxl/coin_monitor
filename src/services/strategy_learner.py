import asyncio
from typing import Dict, List, Any
from src.config import Config
from src.backtest import Backtester
from src.strategies.entry_exit import EntryExitStrategy
from src.connectors.binance import BinanceConnector
from src.utils.logger import logger


class StrategyLearner:
    """策略学习器，自动优化策略参数"""
    
    def __init__(self):
        self.best_strategies = {}
        self.connector = None
    
    async def learn(self, symbols: List[str] = None, days: int = 7) -> Dict:
        """学习最优策略
        
        Args:
            symbols: 要回测的品种列表，如果为None则使用默认的高成交量品种
            days: 回测天数
            
        Returns:
            Dict: 最优策略结果
        """
        logger.info(f"开始策略学习，回测 {days} 天数据...")
        
        if not symbols:
            symbols = self._get_top_volume_symbols(limit=10)
        
        param_grid = {
            'min_total_flow': [10000, 50000, 100000],  # 降低资金流阈值，适应1分钟K线
            'min_ratio': [1.2, 1.5, 2.0],  # 增加更低的买卖比
            'atr_sl_mult': [1.0, 1.5, 2.0],  # 增加更多ATR止损倍数
            'atr_tp_mult': [1.5, 2.0, 2.5],  # 增加更多ATR止盈倍数
            'min_consensus_bars': [1, 2]  # 减少共识K线数要求
        }
        
        all_results = []
        completed = 0
        total = len(symbols)
        
        logger.info(f"将回测 {total} 个品种，请稍候...")
        
        # 初始化连接器并复用
        self.connector = BinanceConnector()
        await self.connector.initialize()
        await self.connector.exchange.load_markets()
        logger.info("✅ Binance 连接已建立，将复用此连接")
        
        for symbol in symbols:
            try:
                cleaned_symbol = symbol.split(':')[0]
                completed += 1
                logger.info(f"回测 [{completed}/{total}]: {cleaned_symbol}...")
                
                bt = Backtester(cleaned_symbol, days, connector=self.connector)
                await bt.prepare_data_v2()
                result = bt.grid_search(param_grid)
                
                if result['best_params']:
                    result['symbol'] = cleaned_symbol
                    all_results.append(result)
                    logger.info(f"  ✅ {cleaned_symbol}: 胜率 {result['best_results']['winrate']:.2%}")
            except Exception as e:
                error_msg = str(e)
                if "Invalid symbol" in error_msg or "Invalid symbol." in error_msg:
                    logger.warning(f"  ⚠️  {cleaned_symbol}: 无效符号")
                else:
                    logger.error(f"  ❌ {cleaned_symbol}: {e}")
            
            # 添加请求间隔控制，避免短时间内发送过多请求
            await asyncio.sleep(Config.RATE_LIMIT_DELAY)
        
        if self.connector:
            await self.connector.close()
            self.connector = None
        
        if all_results:
            # 按胜率排序所有结果
            all_results.sort(key=lambda x: x['best_results']['winrate'], reverse=True)
            
            # 筛选出有实际交易的结果
            valid_results = [r for r in all_results if r['best_results']['total_trades'] > 0]
            
            if valid_results:
                # 计算所有有效结果的平均胜率
                avg_winrate = sum(r['best_results']['winrate'] for r in valid_results) / len(valid_results)
                
                # 筛选胜率高于平均水平的结果
                above_avg_results = [r for r in valid_results if r['best_results']['winrate'] >= avg_winrate]
                
                # 使用足够多的结果来计算最优参数
                num_results_to_use = min(5, len(above_avg_results)) if above_avg_results else min(3, len(valid_results))
                selected_results = above_avg_results[:num_results_to_use] if above_avg_results else valid_results[:num_results_to_use]
                
                best_global_params = self._calculate_best_params(selected_results)
                best_winrate = selected_results[0]['best_results']['winrate']
                best_symbols = [r['symbol'] for r in selected_results]
                
                self.best_strategies['global'] = {
                    'params': best_global_params,
                    'winrate': best_winrate,
                    'symbols': best_symbols
                }
                
                logger.info(f"🎉 策略学习完成！全局最优胜率: {best_winrate:.2%}")
                logger.info(f"   共测试 {len(valid_results)} 个有效品种，使用 {num_results_to_use} 个结果计算最优参数")
                logger.info(f"   平均胜率: {avg_winrate:.2%}")
            else:
                logger.warning("⚠️  所有品种回测失败，未找到有效策略")
                # 使用优化后的默认参数
                self.best_strategies['global'] = {
                    'params': {
                        'min_total_flow': 10000,  # 使用更低的默认值
                        'min_ratio': 1.2,
                        'atr_sl_mult': 1.5,
                        'atr_tp_mult': 2.0,
                        'min_consensus_bars': 1
                    },
                    'winrate': 0.0,
                    'symbols': []
                }
        else:
            logger.warning("⚠️  所有品种回测失败，未找到有效策略")
            # 使用优化后的默认参数
            self.best_strategies['global'] = {
                'params': {
                    'min_total_flow': 10000,  # 使用更低的默认值
                    'min_ratio': 1.2,
                    'atr_sl_mult': 1.5,
                    'atr_tp_mult': 2.0,
                    'min_consensus_bars': 1
                },
                'winrate': 0.0,
                'symbols': []
            }
        
        return self.best_strategies
    
    def _get_top_volume_symbols(self, limit: int = 10) -> List[str]:
        return ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
                'DOGE/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT', 'MATIC/USDT']
    
    def _calculate_best_params(self, top_results: List[Dict]) -> Dict:
        param_counts = {
            'min_total_flow': {},
            'min_ratio': {},
            'atr_sl_mult': {},
            'atr_tp_mult': {},
            'min_consensus_bars': {}
        }
        
        for result in top_results:
            params = result['best_params']
            for param_name, param_value in params.items():
                if param_value not in param_counts[param_name]:
                    param_counts[param_name][param_value] = 0
                param_counts[param_name][param_value] += 1
        
        best_params = {}
        for param_name, counts in param_counts.items():
            best_value = max(counts.items(), key=lambda x: x[1])[0]
            best_params[param_name] = best_value
        
        return best_params
    
    def learn_sync(self, symbols: List[str] = None, days: int = 7) -> Dict:
        return asyncio.run(self.learn(symbols=symbols, days=days))
