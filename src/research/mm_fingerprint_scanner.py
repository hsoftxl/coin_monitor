import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
from loguru import logger
import ccxt.async_support as ccxt

# 添加项目根目录到路径
sys.path.append(os.getcwd())

# 导入指纹管理器
from src.research.fingerprint_manager import FingerprintManager

class MMFingerprintScanner:
    def __init__(self):
        # 将输出目录改为同级的 data 目录
        self.output_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.output_dir, exist_ok=True)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        self.results = []
        
        # 初始化指纹管理器
        self.fingerprint_manager = FingerprintManager()
        
        # 目标指纹特征 (基于 LIGHT 分析结果)
        self.TARGET_PIR_MIN = 1.2
        self.TARGET_IGNITION_HOURS = [8, 9] # UTC 8-9 时
        self.TARGET_ACCUMULATION_RATIO = 0.15 # 15% 以上低波期
        
        # 新增：指标细分参数
        self.BIG_ORDER_THRESHOLD = 5000  # 大单阈值 (USDT)
        self.TAKER_BUY_RATIO_THRESHOLD = 0.6  # 主动买入占比阈值
        self.VOLUME_SPIKE_THRESHOLD = 6.0  # 成交量峰值阈值
        self.PRICE_PUMP_THRESHOLD = 1.2  # 价格涨幅阈值
        self.SHADOW_RATIO_THRESHOLD = 1.2  # 上影线比例阈值
        
    async def get_all_symbols(self, only_light=False):
        markets = await self.exchange.load_markets()
        
        # 如果 only_light 为 True，只返回 LIGHT 币
        if only_light:
            light_symbol = next((s for s, m in markets.items() 
                              if (m.get('type') == 'swap' or 'swap' in m.get('info', {}).get('contractType', '').lower()) 
                              and ('LIGHT' in s) 
                              and (s.endswith('/USDT') or s.endswith('USDT'))), None)
            symbols = [light_symbol] if light_symbol else []
            logger.info(f"Using only LIGHT symbol: {symbols}")
            return symbols
        
        # 否则返回所有 USDT 永续合约
        symbols = []
        for s, m in markets.items():
            # 检查是否是永续合约
            is_swap = m.get('type') == 'swap' or 'swap' in m.get('info', {}).get('contractType', '').lower()
            # 检查是否是 USDT 计价
            is_usdt = s.endswith('/USDT') or s.endswith('USDT')
            if is_swap and is_usdt:
                symbols.append(s)
        
        logger.info(f"Found {len(symbols)} USDT-SWAP symbols on Binance")
        return symbols

    async def analyze_symbol(self, symbol, use_specific_periods=True):
        """
        分析单个币种的指纹特征
        
        Args:
            symbol: 币种符号
            use_specific_periods: 是否使用指定的主力做市时间段（2025-12-18 至 2025-12-22 和 2025-12-30 至 2026-01-02）
        """
        try:
            if use_specific_periods:
                # 主力做市时间段
                periods = [
                    # 时段 1: 2025-12-18 00:00 至 2025-12-22 23:59
                    {
                        'start': datetime(2025, 12, 18, 0, 0),
                        'end': datetime(2025, 12, 22, 23, 59)
                    },
                    # 时段 2: 2025-12-30 00:00 至 2026-01-02 23:59
                    {
                        'start': datetime(2025, 12, 30, 0, 0),
                        'end': datetime(2026, 1, 2, 23, 59)
                    }
                ]
                
                all_ohlcv = []
                for period in periods:
                    # 将 datetime 转换为 timestamp（毫秒）
                    start_ts = int(period['start'].timestamp() * 1000)
                    end_ts = int(period['end'].timestamp() * 1000)
                    
                    # 计算需要获取的 K 线数量（每分钟一根）
                    minutes = int((end_ts - start_ts) / (1000 * 60)) + 1
                    
                    logger.info(f"📊 Fetching {minutes} candles for {symbol} from {period['start']} to {period['end']}")
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, '1m', since=start_ts, limit=minutes)
                    if ohlcv:
                        all_ohlcv.extend(ohlcv)
                        logger.info(f"✅ Fetched {len(ohlcv)} candles for period {period['start']} to {period['end']}")
                
                ohlcv = all_ohlcv
            else:
                # 默认使用最近3天的数据
                days = 3
                start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
                ohlcv = await self.exchange.fetch_ohlcv(symbol, '1m', since=start_time, limit=1440 * days)
            
            if not ohlcv:
                logger.debug(f"{symbol}: No OHLCV data fetched.")
                return None
                
            if len(ohlcv) < 100: # 放宽限制用于调试
                logger.debug(f"{symbol}: Data length too short ({len(ohlcv)})")
                return None
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 基础指标计算
            df['price_pct'] = df['close'].pct_change() * 100
            df['amount'] = df['close'] * df['volume']
            df['vol_ma'] = df['volume'].rolling(window=20).mean()
            df['vol_spike'] = df['volume'] / df['vol_ma']
            df['vol_ma_60'] = df['volume'].rolling(window=60).mean()
            df['vol_spike_60'] = df['volume'] / df['vol_ma_60']
            
            # 新增指标 1: 资金流向分析
            # 预估净流: 收盘 > 开盘 设为流入
            df['est_flow'] = np.where(df['close'] > df['open'], df['amount'], -df['amount'])
            df['cum_est_flow'] = df['est_flow'].cumsum()
            df['flow_ratio'] = df['est_flow'].abs() / df['amount']
            
            # 新增指标 2: 买卖盘特征
            # 主动买入占比 (基于 K 线涨跌)
            df['taker_buy_ratio'] = np.where(df['close'] > df['open'], 
                                            df['volume'] / df['volume'], 
                                            0)
            df['avg_taker_buy_ratio'] = df['taker_buy_ratio'].rolling(window=10).mean()
            
            # 新增指标 3: 大单占比模拟
            # 基于成交额大小划分大单
            df['is_big_order'] = df['amount'] > self.BIG_ORDER_THRESHOLD
            
            # 新增指标 4: 价格波动特征
            # 连续上涨/下跌天数
            df['is_up'] = df['price_pct'] > 0
            df['up_streak'] = df['is_up'].groupby((~df['is_up']).cumsum()).cumsum()
            df['down_streak'] = (~df['is_up']).groupby(df['is_up'].cumsum()).cumsum()
            
            # 新增指标 5: 波动率特征
            df['volatility'] = df['price_pct'].rolling(window=20).std()
            df['volatility_ratio'] = df['volatility'] / df['volatility'].rolling(window=60).mean()
            
            # 新增指标 6: 价格与成交量相关性
            df['price_vol_corr'] = df['price_pct'].rolling(window=30).corr(df['volume'])
            
            # 1. PIR 计算 (拉升效率)
            # 预估净流: 收盘 > 开盘 设为流入
            df['est_flow'] = np.where(df['close'] > df['open'], df['amount'], -df['amount'])
            up_minutes = df[(df['price_pct'] > 0.5) & (df['amount'] > 10000)].copy()
            if len(up_minutes) < 5:
                return None
                
            pir_median = (up_minutes['price_pct'] / (up_minutes['est_flow'] / 1e6)).median()
            
            # 2. 点火次数统计（移除时间窗口分析）
            ignitions = df[(df['vol_spike'] > self.VOLUME_SPIKE_THRESHOLD) & (df['price_pct'] > self.PRICE_PUMP_THRESHOLD)]
            total_ignitions = len(ignitions)
            # 移除时间窗口匹配相关逻辑
            window_score = 0
                
            # 3. 影线分析
            df['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['close'] * 100
            df['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['close'] * 100
            heavy_shadow_count = len(df[df['upper_shadow'] > self.SHADOW_RATIO_THRESHOLD])
            avg_upper_shadow = df['upper_shadow'].mean()
            avg_lower_shadow = df['lower_shadow'].mean()
            
            # 4. 波动率平稳期占比
            rolling_std = df['close'].rolling(window=60).std() / df['close'].rolling(window=60).mean() * 100
            low_vol_ratio = len(rolling_std[rolling_std < rolling_std.quantile(0.2)]) / len(df)
            
            # 5. 新增：资金流向特征
            # 正资金流入占比
            positive_flow_ratio = len(df[df['est_flow'] > 0]) / len(df)
            avg_flow = df['est_flow'].mean()
            
            # 6. 新增：大单特征
            big_order_volume = df[df['is_big_order']]['volume'].sum()
            total_volume = df['volume'].sum()
            big_order_ratio = big_order_volume / total_volume if total_volume > 0 else 0
            
            # 7. 新增：连续上涨动能
            strong_up_moves = len(df[(df['price_pct'] > 2.0) & (df['vol_spike'] > 4.0)])
            max_up_streak = df['up_streak'].max()
            
            # 8. 新增：成交量集中度
            # 成交量前 10% 占总成交量比例
            top_10_vol = df['volume'].nlargest(int(len(df) * 0.1)).sum()
            volume_concentration = top_10_vol / total_volume if total_volume > 0 else 0
            
            # 9. 新增：平均波动特征
            avg_price_pct = df['price_pct'].mean()
            max_1m_pump = df['price_pct'].max()
            
            # 10. 新增：价格与成交量相关性
            avg_price_vol_corr = df['price_vol_corr'].mean() if 'price_vol_corr' in df.columns else 0
            
            # 优化评分机制 (满分 100)
            # 移除时间窗口匹配，调整权重分配
            # 新权重：PIR (30%)、资金流向 (20%)、成交量特征 (20%)、价格特征 (20%)、形态特征 (10%)
            score = 0
            
            # 1. PIR 表现 (30分) - 增加5分
            if pir_median > self.TARGET_PIR_MIN:
                score += 30 * min(pir_median / (self.TARGET_PIR_MIN * 2), 1.0)
            
            # 2. 资金流向特征 (20分) - 增加5分
            # 正资金流入占比
            if positive_flow_ratio > 0.5:
                score += 20 * min(positive_flow_ratio, 1.0)
            
            # 3. 成交量特征 (20分) - 增加5分
            # 成交量峰值情况
            high_vol_spikes = len(df[(df['vol_spike'] > 4.0) & (df['price_pct'] > 0.5)])
            score += min(high_vol_spikes * 0.7, 15)  # 增加峰值权重
            # 大单占比
            if big_order_ratio > 0.3:
                score += 5
            
            # 4. 价格波动特征 (20分) - 增加5分
            # 连续上涨动能
            score += min(strong_up_moves * 2.5, 15)  # 增加上涨动能权重
            # 波动率平稳期
            if low_vol_ratio > self.TARGET_ACCUMULATION_RATIO:
                score += 5
            
            # 5. 形态特征 (10分) - 保持不变
            # 影线特征
            if avg_upper_shadow < 0.5:  # 上影线短，多头强势
                score += 5
            if avg_lower_shadow > 1.0:  # 下影线长，支撑强劲
                score += 5
            
            # 最终评分限制在 0-100 之间
            score = max(0, min(100, score))
            
            return {
                'symbol': symbol,
                'score': score,
                # 基础指标
                'pir_median': pir_median,
                'window_hit_rate': window_score,
                'low_vol_ratio': low_vol_ratio,
                'heavy_shadow_count': heavy_shadow_count,
                'total_ignitions': total_ignitions,
                'max_1m_pump': max_1m_pump,
                # 新增指标：资金流向
                'positive_flow_ratio': positive_flow_ratio,
                'avg_flow': avg_flow,
                # 新增指标：买卖盘特征
                'avg_taker_buy_ratio': df['avg_taker_buy_ratio'].mean(),
                # 新增指标：大单特征
                'big_order_ratio': big_order_ratio,
                # 新增指标：价格波动
                'strong_up_moves': strong_up_moves,
                'max_up_streak': max_up_streak,
                'avg_price_pct': avg_price_pct,
                # 新增指标：成交量特征
                'volume_concentration': volume_concentration,
                # 新增指标：形态特征
                'avg_upper_shadow': avg_upper_shadow,
                'avg_lower_shadow': avg_lower_shadow,
                # 新增指标：相关性
                'avg_price_vol_corr': avg_price_vol_corr,
                'volatility_ratio': df['volatility_ratio'].mean()
            }
            
        except Exception as e:
            logger.debug(f"{symbol}: Exception during analysis: {e}")
            return {'symbol': symbol, 'score': 0, 'error': str(e)}

    async def run_scan(self, only_light=True):
        """
        运行指纹扫描
        
        Args:
            only_light: 是否只扫描 LIGHT 币
        """
        # 默认只扫描 LIGHT 币，使用特定时间段
        symbols = await self.get_all_symbols(only_light=only_light)
        logger.info(f"Starting parallel scanning for {len(symbols)} symbols...")
        
        # 降低并发，对于单个币种可以设置为 1
        sem = asyncio.Semaphore(1 if only_light else 5) 
        
        async def sem_analyze(symbol):
            async with sem:
                # 对于 LIGHT 币，强制使用特定时间段
                res = await self.analyze_symbol(symbol, use_specific_periods=True)
                if res and res.get('score', 0) >= 1:
                    print(f"   [PROCESSED] {symbol} | Score: {res['score']:.1f}", end='\r')
                return res

        tasks = [sem_analyze(s) for s in symbols]
        all_results = await asyncio.gather(*tasks)
        
        self.results = [r for r in all_results if r is not None]
        
        if not self.results:
            logger.warning("No symbols analyzed successfully.")
            await self.exchange.close()
            return

        # 过滤掉报错的记录
        valid_results = [r for r in self.results if 'score' in r]
        valid_results.sort(key=lambda x: x['score'], reverse=True)
        
        # 导出结果
        df_res = pd.DataFrame(valid_results)
        df_res.to_csv(f"{self.output_dir}/scan_results.csv", index=False)
        logger.info(f"Scan complete. Total: {len(valid_results)}. Top results saved.")
        
        print(f"\n\n--- LIGHT 币种在结果中的位置 ---")
        light_entry = df_res[df_res['symbol'] == 'LIGHT/USDT']
        print(light_entry if not light_entry.empty else "Not Found in results!")

        print("\n\n--- 扫描结果 Top 20 (主力特征评分排名) ---")
        # 输出更多关键指标
        cols_to_print = [c for c in ['symbol', 'score', 'pir_median', 'window_hit_rate', 'total_ignitions', 
                                     'positive_flow_ratio', 'big_order_ratio', 'strong_up_moves', 
                                     'volume_concentration', 'max_1m_pump'] if c in df_res.columns]
        print(df_res.head(20)[cols_to_print])
        
        # 保存扫描结果为指纹
        print(f"\n\n--- 保存指纹数据 ---")
        saved_count = 0
        for _, row in df_res.iterrows():
            # 只保存评分较高的指纹
            if row['score'] >= 50:
                # 提取关键指标
                metrics = {
                    'pir_median': row.get('pir_median', 0),
                    'window_hit_rate': row.get('window_hit_rate', 0),
                    'positive_flow_ratio': row.get('positive_flow_ratio', 0),
                    'big_order_ratio': row.get('big_order_ratio', 0),
                    'strong_up_moves': row.get('strong_up_moves', 0),
                    'volume_concentration': row.get('volume_concentration', 0),
                    'avg_upper_shadow': row.get('avg_upper_shadow', 0),
                    'avg_lower_shadow': row.get('avg_lower_shadow', 0),
                    'volatility_ratio': row.get('volatility_ratio', 0)
                }
                # 保存指纹
                self.fingerprint_manager.add_fingerprint(row['symbol'], metrics, row['score'])
                saved_count += 1
        print(f"✅ 成功保存 {saved_count} 个指纹")
        
        # 输出指纹统计信息
        stats = self.fingerprint_manager.get_fingerprint_stats()
        print(f"📊 指纹统计: 总计 {stats['total']} 个, 活跃 {stats['active']} 个, 平均评分 {stats['avg_score']}")
        
        await self.exchange.close()

if __name__ == "__main__":
    scanner = MMFingerprintScanner()
    asyncio.run(scanner.run_scan())
