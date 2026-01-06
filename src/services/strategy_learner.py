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
            'min_total_flow': [100000, 200000, 300000],
            'min_ratio': [1.5, 2.0, 2.5],
            'atr_sl_mult': [1.5, 2.0],
            'atr_tp_mult': [2.0, 3.0],
            'min_consensus_bars': [1, 2, 3]
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
            all_results.sort(key=lambda x: x['best_results']['winrate'], reverse=True)
            top_results = all_results[:3]
            best_global_params = self._calculate_best_params(top_results)
            
            self.best_strategies['global'] = {
                'params': best_global_params,
                'winrate': top_results[0]['best_results']['winrate'],
                'symbols': [r['symbol'] for r in top_results]
            }
            
            logger.info(f"🎉 策略学习完成！全局最优胜率: {self.best_strategies['global']['winrate']:.2%}")
        else:
            logger.warning("⚠️  所有品种回测失败，未找到有效策略")
            self.best_strategies['global'] = {
                'params': {
                    'min_total_flow': 100000,
                    'min_ratio': 1.5,
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
