import asyncio
from typing import List, Dict
from src.connectors.binance import BinanceConnector
from src.processors.data_processor import DataProcessor
from src.strategies.entry_exit import EntryExitStrategy
from src.config import Config
from src.utils.logger import logger


class SymbolSelector:
    """品种筛选器，使用最优策略筛选可交易品种"""
    
    def __init__(self, strategy: EntryExitStrategy):
        """初始化品种筛选器
        
        Args:
            strategy: 用于筛选的策略对象
        """
        self.strategy = strategy
    
    async def select_symbols(self, symbols: List[str]) -> List[str]:
        """使用最优策略筛选可交易品种
        
        Args:
            symbols: 要筛选的品种列表
            
        Returns:
            List[str]: 符合条件的可交易品种列表
        """
        logger.info(f"开始筛选可交易品种，共 {len(symbols)} 个...")
        selected = []
        
        # 初始化连接器
        connector = BinanceConnector()
        await connector.initialize()
        
        for symbol in symbols:
            try:
                # 修复符号格式，移除冒号并转换为正确格式
                cleaned_symbol = symbol.split(':')[0]  # 移除 :USDT 后缀
                
                # 获取最新数据（50根1分钟K线）
                candles = await connector.fetch_standard_candles(cleaned_symbol, limit=50)
                if not candles or len(candles) < 50:
                    logger.debug(f"  {cleaned_symbol}: 数据不足，跳过")
                    continue
                
                # 处理数据
                df = DataProcessor.process_candles(candles)
                
                # 计算指标（模拟现有策略的指标计算）
                metrics = self._calculate_metrics(df)
                
                # 评估策略
                platform_metrics = {'binance': metrics}
                consensus = "看涨" if metrics['cumulative_net_flow'] > Config.STRATEGY_MIN_TOTAL_FLOW else "看跌"
                signals = []
                
                # 使用最优策略评估
                result = self.strategy.evaluate(
                    platform_metrics, 
                    consensus, 
                    signals, 
                    cleaned_symbol
                )
                
                # 如果策略建议入场，添加到选中列表
                if result['action'] == 'ENTRY':
                    selected.append(cleaned_symbol)
                    logger.info(f"  ✅ {cleaned_symbol}: 符合交易条件")
                else:
                    logger.debug(f"  ❌ {cleaned_symbol}: 不符合交易条件")
            except Exception as e:
                logger.error(f"  ⚠️  筛选 {symbol} 失败: {e}")
        
        await connector.close()
        logger.info(f"品种筛选完成！共选中 {len(selected)} 个品种")
        return selected
    
    def _calculate_metrics(self, df) -> Dict:
        """计算品种的关键指标
        
        Args:
            df: 品种的K线数据
            
        Returns:
            Dict: 计算后的指标
        """
        # 这里简化了指标计算，实际应使用TakerFlowAnalyzer
        # 为了快速实现，我们计算一些基础指标
        metrics = {
            'cumulative_net_flow': 0.0,
            'buy_sell_ratio': 1.0,
            'current_price': df['close'].iloc[-1] if not df.empty else 0.0,
            'support_low': df['low'].min() if not df.empty else 0.0,
            'resistance_high': df['high'].max() if not df.empty else 0.0,
            'atr': 0.0
        }
        
        # 计算ATR（平均真实波动幅度）
        if len(df) >= 14:
            # 简单ATR计算
            tr = df['high'] - df['low']
            metrics['atr'] = tr.rolling(window=14).mean().iloc[-1]
        
        # 计算简单的资金流向和买卖比率
        if len(df) >= 10:
            # 假设最近10根K线的上涨成交量为买入，下跌成交量为卖出
            buy_vol = df['volume'][(df['close'] > df['open'])].sum()
            sell_vol = df['volume'][(df['close'] <= df['open'])].sum()
            
            # 计算买卖比率
            if sell_vol > 0:
                metrics['buy_sell_ratio'] = buy_vol / sell_vol
            
            # 计算资金流向
            metrics['cumulative_net_flow'] = (buy_vol - sell_vol) * df['close'].iloc[-1]
        
        return metrics
