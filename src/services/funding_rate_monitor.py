import asyncio
import time
from typing import Dict, List
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OKXConnector
from src.connectors.bybit import BybitConnector
from src.services.notification import NotificationService
from src.config import Config
from src.utils.logger import logger


class FundingRateMonitor:
    """
    资金费率监控器，检测资金费率大于阈值的交易对并发送通知
    """
    
    def __init__(self):
        # 只初始化已启用的交易所
        self.connectors = {}
        if Config.EXCHANGES.get('binance', False):
            self.connectors['binance'] = BinanceConnector()
        if Config.EXCHANGES.get('okx', False):
            self.connectors['okx'] = OKXConnector()
        if Config.EXCHANGES.get('bybit', False):
            self.connectors['bybit'] = BybitConnector()
        
        self.notification_service = NotificationService()
        self.is_running = False
        self.last_checked = {}
        logger.info(f"初始化资金费率监控器，启用的交易所: {list(self.connectors.keys())}")
    
    async def initialize(self):
        """
        初始化交易所连接器
        """
        for name, connector in self.connectors.items():
            if Config.EXCHANGES.get(name, False):
                try:
                    await connector.initialize()
                    logger.info(f"✅ 成功初始化 {name} 连接器")
                except Exception as e:
                    logger.error(f"❌ 初始化 {name} 连接器失败: {e}")
    
    async def fetch_funding_rate(self, connector, symbol: str) -> Dict:
        """
        从交易所获取资金费率数据
        
        Args:
            connector: 交易所连接器
            symbol: 交易对
            
        Returns:
            包含资金费率的字典
        """
        try:
            if not hasattr(connector, 'exchange') or connector.exchange is None:
                logger.error(f"❌ {connector.exchange_id} 连接器未初始化")
                return None
            
            # 根据交易所类型，使用不同的API调用方式
            if connector.exchange_id == 'binance':
                # Binance特定API
                try:
                    market = connector.exchange.market(symbol)
                    if Config.MARKET_TYPE == 'future':
                        # 使用CCXT标准方法，它会处理不同API返回格式的差异
                        if hasattr(connector.exchange, 'fetch_funding_rate'):
                            funding_rate_data = await connector.exchange.fetch_funding_rate(symbol)
                            # 检查返回数据结构，确保包含funding_rate字段
                            if 'funding_rate' not in funding_rate_data:
                                # 尝试从info中提取资金费率（Binance可能的格式）
                                if 'info' in funding_rate_data:
                                    # Binance info字段中可能包含的资金费率字段名
                                    possible_fields = ['fundingRate', 'funding_rate', 'lastFundingRate', 'last_funding_rate']
                                    for field in possible_fields:
                                        if field in funding_rate_data['info']:
                                            funding_rate_data['funding_rate'] = float(funding_rate_data['info'][field])
                                            break
                                    else:
                                        logger.warning(f"⚠️ Binance 返回的资金费率数据中没有找到funding_rate字段: {funding_rate_data}")
                                        return None
                            return funding_rate_data
                        else:
                            # 备用方法：使用统一的API调用方式
                            funding_rates = await connector.exchange.fetch_funding_rates()
                            # 查找当前交易对的资金费率
                            for fr in funding_rates:
                                if fr['symbol'] == symbol:
                                    # 检查返回数据结构，确保包含funding_rate字段
                                    if 'funding_rate' not in fr:
                                        # 尝试从info中提取资金费率
                                        if 'info' in fr:
                                            possible_fields = ['fundingRate', 'funding_rate', 'lastFundingRate', 'last_funding_rate']
                                            for field in possible_fields:
                                                if field in fr['info']:
                                                    fr['funding_rate'] = float(fr['info'][field])
                                                    break
                                            else:
                                                logger.warning(f"⚠️ Binance 返回的资金费率数据中没有找到funding_rate字段: {fr}")
                                                continue
                                    return fr
                            return None
                except Exception as e:
                    logger.error(f"❌ Binance API 获取 {symbol} 资金费率失败: {e}")
                    logger.exception(e)
                    return None
            elif connector.exchange_id == 'okx' or connector.exchange_id == 'bybit':
                # 使用CCXT标准方法，统一处理所有交易所
                try:
                    if hasattr(connector.exchange, 'fetch_funding_rate'):
                        funding_rate_data = await connector.exchange.fetch_funding_rate(symbol)
                        # 检查返回数据结构，确保包含funding_rate字段
                        if 'funding_rate' not in funding_rate_data:
                            # 尝试从info中提取fundingRate（OKX/Bybit可能的格式）
                            if 'info' in funding_rate_data:
                                possible_fields = ['fundingRate', 'funding_rate']
                                for field in possible_fields:
                                    if field in funding_rate_data['info']:
                                        funding_rate_data['funding_rate'] = float(funding_rate_data['info'][field])
                                        break
                                else:
                                    logger.warning(f"⚠️ {connector.exchange_id} 返回的资金费率数据中没有找到funding_rate字段: {funding_rate_data}")
                                    return None
                        return funding_rate_data
                    else:
                        # 备用方法：获取所有资金费率然后过滤
                        funding_rates = await connector.exchange.fetch_funding_rates()
                        # 查找当前交易对的资金费率
                        for fr in funding_rates:
                            if fr['symbol'] == symbol:
                                # 检查返回数据结构，确保包含funding_rate字段
                                if 'funding_rate' not in fr:
                                    # 尝试从info中提取fundingRate（OKX/Bybit可能的格式）
                                    if 'info' in fr:
                                        possible_fields = ['fundingRate', 'funding_rate']
                                        for field in possible_fields:
                                            if field in fr['info']:
                                                fr['funding_rate'] = float(fr['info'][field])
                                                break
                                        else:
                                            logger.warning(f"⚠️ {connector.exchange_id} 返回的资金费率数据中没有找到funding_rate字段: {fr}")
                                            continue
                                return fr
                        return None
                except Exception as e:
                    logger.error(f"❌ {connector.exchange_id.upper()} API 获取 {symbol} 资金费率失败: {e}")
                    logger.exception(e)
                    return None
            
            # 其他交易所使用CCXT标准方法
            try:
                if hasattr(connector.exchange, 'fetch_funding_rate'):
                    funding_rate_data = await connector.exchange.fetch_funding_rate(symbol)
                    # 检查返回数据结构，确保包含funding_rate字段
                    if 'funding_rate' not in funding_rate_data:
                        # 尝试从info中提取资金费率
                        if 'info' in funding_rate_data:
                            possible_fields = ['fundingRate', 'funding_rate', 'lastFundingRate', 'last_funding_rate']
                            for field in possible_fields:
                                if field in funding_rate_data['info']:
                                    funding_rate_data['funding_rate'] = float(funding_rate_data['info'][field])
                                    break
                            else:
                                logger.warning(f"⚠️ {connector.exchange_id} 返回的资金费率数据中没有找到funding_rate字段: {funding_rate_data}")
                                return None
                    return funding_rate_data
                elif hasattr(connector.exchange, 'fetch_funding_rates'):
                    # 备用方法：获取所有资金费率然后过滤
                    funding_rates = await connector.exchange.fetch_funding_rates()
                    for fr in funding_rates:
                        if fr['symbol'] == symbol:
                            # 检查返回数据结构，确保包含funding_rate字段
                            if 'funding_rate' not in fr:
                                # 尝试从info中提取资金费率
                                if 'info' in fr:
                                    possible_fields = ['fundingRate', 'funding_rate', 'lastFundingRate', 'last_funding_rate']
                                    for field in possible_fields:
                                        if field in fr['info']:
                                            fr['funding_rate'] = float(fr['info'][field])
                                            break
                                    else:
                                        logger.warning(f"⚠️ {connector.exchange_id} 返回的资金费率数据中没有找到funding_rate字段: {fr}")
                                        continue
                            return fr
            except Exception as e:
                logger.error(f"❌ {connector.exchange_id.upper()} CCXT 方法获取 {symbol} 资金费率失败: {e}")
                logger.exception(e)
                
            return None
        except Exception as e:
            logger.error(f"❌ 获取 {symbol} 资金费率失败: {e}")
            logger.exception(e)
            return None
    
    async def fetch_all_funding_rates(self, exchange_name: str, connector) -> List[Dict]:
        """
        获取交易所所有合约交易对的资金费率
        
        Args:
            exchange_name: 交易所名称
            connector: 交易所连接器
            
        Returns:
            资金费率列表
        """
        try:
            # 获取交易所支持的所有合约交易对
            logger.info(f"🔍 开始获取 {exchange_name} 资金费率，当前交易所符号数量: {len(connector.exchange.symbols)}")
            
            if connector.exchange_id == 'binance':
                # Binance合约交易对
                futures_symbols = [symbol for symbol in connector.exchange.symbols if '/USDT' in symbol and ':USDT' in symbol]
                logger.info(f"📋 找到 {len(futures_symbols)} 个 Binance 合约交易对")
            elif connector.exchange_id == 'okx':
                # OKX合约交易对
                futures_symbols = [symbol for symbol in connector.exchange.symbols if ':USDT' in symbol]
                logger.info(f"📋 找到 {len(futures_symbols)} 个 OKX 合约交易对")
            elif connector.exchange_id == 'bybit':
                # Bybit合约交易对
                futures_symbols = [symbol for symbol in connector.exchange.symbols if '/USDT' in symbol and ':USDT' in symbol]
                logger.info(f"📋 找到 {len(futures_symbols)} 个 Bybit 合约交易对")
            else:
                futures_symbols = []
                logger.info(f"📋 未找到 {exchange_name} 合约交易对")
            
            if not futures_symbols:
                logger.warning(f"⚠️  {exchange_name} 没有找到符合条件的合约交易对")
                return []
            
            # 只保留前20个交易对进行监控，提高效率
            # 后续可以优化为从主程序获取高成交额交易对列表
            filtered_symbols = futures_symbols[:20]
            logger.info(f"📋 过滤后需要监控的交易对数量: {len(filtered_symbols)}")
            
            if not filtered_symbols:
                logger.warning(f"⚠️  {exchange_name} 没有符合条件的交易对")
                return []
            
            funding_rates = []
            for symbol in filtered_symbols:
                # 跳过排除的交易对
                if any(excluded in symbol for excluded in Config.EXCLUDED_SYMBOLS):
                    logger.debug(f"⏭️  跳过排除的交易对: {symbol}")
                    continue
                    
                # 检查冷却时间，避免频繁请求
                if symbol in self.last_checked and time.time() - self.last_checked[symbol] < Config.FUNDING_RATE_CHECK_INTERVAL:
                    logger.debug(f"⏳ {symbol} 处于冷却期，跳过")
                    continue
                    
                logger.debug(f"📡 获取 {symbol} 资金费率...")
                # 获取资金费率
                funding_rate_data = await self.fetch_funding_rate(connector, symbol)
                if funding_rate_data:
                    logger.debug(f"✅ 成功获取 {symbol} 资金费率: {funding_rate_data['funding_rate'] * 100:.4f}%")
                    # 获取当前价格
                    try:
                        ticker = await connector.fetch_ticker(symbol)
                        funding_rate_data['price'] = ticker['last']
                        # 处理价格可能为None的情况
                        if funding_rate_data['price'] is not None:
                            logger.debug(f"📊 {symbol} 当前价格: ${funding_rate_data['price']:.4f}")
                        else:
                            logger.debug(f"📊 {symbol} 当前价格: 暂无数据")
                            funding_rate_data['price'] = 0
                    except Exception as e:
                        logger.error(f"❌ 获取 {symbol} 价格失败: {e}")
                        funding_rate_data['price'] = 0
                    
                    funding_rates.append(funding_rate_data)
                    self.last_checked[symbol] = time.time()
                    
                    # 立即检查并发送通知，不需要等待所有交易对处理完毕
                    funding_rate = funding_rate_data['funding_rate'] * 100  # 转换为百分比
                    logger.debug(f"🔍 检查 {symbol} 资金费率: {funding_rate:.4f}%，阈值: {Config.FUNDING_RATE_THRESHOLD}%")
                    logger.debug(f"📋 当前配置阈值: {Config.FUNDING_RATE_THRESHOLD}%")
                    logger.debug(f"🧮 比较结果: {funding_rate} >= {Config.FUNDING_RATE_THRESHOLD} = {funding_rate >= Config.FUNDING_RATE_THRESHOLD}")
                    
                    if funding_rate >= Config.FUNDING_RATE_THRESHOLD:
                        logger.warning(f"⚡ 检测到高资金费率: {symbol} @ {exchange_name} - {funding_rate:.4f}% (阈值: {Config.FUNDING_RATE_THRESHOLD}%)")
                        logger.info(f"📤 准备发送资金费率警报...")
                        logger.info(f"📋 通知服务初始化状态: {self.notification_service is not None}")
                        
                        try:
                            logger.debug(f"📝 调用通知服务发送资金费率警报")
                            await self.notification_service.send_funding_rate_alert(funding_rate_data, symbol, exchange_name)
                            logger.info(f"✅ 成功发送 {symbol} 资金费率警报")
                        except Exception as notify_e:
                            logger.error(f"❌ 发送 {symbol} 资金费率警报失败: {notify_e}")
                            logger.exception(notify_e)
                    else:
                        logger.debug(f"ℹ️ {symbol} 资金费率 {funding_rate:.4f}% 未超过阈值 {Config.FUNDING_RATE_THRESHOLD}%")
                        logger.debug(f"📝 资金费率数据完整度检查: funding_rate={funding_rate_data['funding_rate']}, price={funding_rate_data.get('price')}")
                else:
                    logger.debug(f"❌ 无法获取 {symbol} 资金费率")
                    
                # 避免请求过快
                await asyncio.sleep(Config.RATE_LIMIT_DELAY / 2)  # 缩短延迟时间
            
            logger.info(f"📈 成功获取 {len(funding_rates)} 个交易对的资金费率数据")
            return funding_rates
        except Exception as e:
            logger.error(f"❌ 获取 {exchange_name} 资金费率列表失败: {e}")
            logger.exception(e)  # 记录详细错误信息
            return []
    
    async def check_and_notify(self):
        """
        检查所有交易所的资金费率，发送超过阈值的通知
        """
        logger.info(f"🔍 开始检查所有交易所的资金费率，当前配置阈值: {Config.FUNDING_RATE_THRESHOLD}%")
        logger.debug(f"📋 已初始化的交易所连接器: {list(self.connectors.keys())}")
        logger.debug(f"📋 通知服务实例: {self.notification_service}")
        
        for exchange_name, connector in self.connectors.items():
            logger.debug(f"🔄 开始处理交易所: {exchange_name}")
            if not Config.EXCHANGES.get(exchange_name, False):
                logger.debug(f"⏭️  跳过未启用的交易所: {exchange_name}")
                continue
                
            logger.info(f"📋 处理交易所: {exchange_name}")
            
            try:
                # 获取所有交易对的资金费率
                logger.info(f"📡 正在获取 {exchange_name} 的资金费率数据...")
                funding_rates = await self.fetch_all_funding_rates(exchange_name, connector)
                logger.info(f"✅ 成功获取 {exchange_name} 的 {len(funding_rates)} 个交易对资金费率数据")
                logger.debug(f"📊 资金费率数据样本: {funding_rates[:1] if funding_rates else '无'}")
                
                if not funding_rates:
                    logger.debug(f"ℹ️  {exchange_name} 没有符合条件的交易对数据")
                    continue
                
                # 检查并发送通知
                logger.info(f"🔍 开始检查 {exchange_name} 的 {len(funding_rates)} 个交易对是否超过阈值")
                alert_count = 0
                
                for funding_data in funding_rates:
                    funding_rate = funding_data['funding_rate'] * 100  # 转换为百分比
                    symbol = funding_data['symbol']
                    
                    logger.debug(f"📊 检查 {symbol}: {funding_rate:.4f}% (阈值: {Config.FUNDING_RATE_THRESHOLD}%)")
                    logger.debug(f"📝 资金数据完整性: {all(k in funding_data for k in ['funding_rate', 'symbol', 'price'])}")
                    
                    # 检查是否超过阈值
                    logger.debug(f"🧮 比较结果: {funding_rate} >= {Config.FUNDING_RATE_THRESHOLD} = {funding_rate >= Config.FUNDING_RATE_THRESHOLD}")
                    if funding_rate >= Config.FUNDING_RATE_THRESHOLD:
                        alert_count += 1
                        logger.warning(f"⚡ 检测到高资金费率: {symbol} @ {exchange_name} - {funding_rate:.4f}% (阈值: {Config.FUNDING_RATE_THRESHOLD}%)")
                        logger.info(f"📤 准备发送资金费率警报...")
                        
                        try:
                            logger.debug(f"📞 调用 send_funding_rate_alert 方法")
                            await self.notification_service.send_funding_rate_alert(funding_data, symbol, exchange_name)
                            logger.info(f"✅ 成功发送 {symbol} 资金费率警报")
                        except Exception as notify_e:
                            logger.error(f"❌ 发送 {symbol} 资金费率警报失败: {notify_e}")
                            logger.exception(notify_e)
                    else:
                        logger.debug(f"ℹ️  {symbol} 资金费率 {funding_rate:.4f}% 未超过阈值 {Config.FUNDING_RATE_THRESHOLD}%")
                
                logger.info(f"📊 {exchange_name} 检查完成，共触发 {alert_count} 个警报")
                        
            except Exception as e:
                logger.error(f"❌ 检查 {exchange_name} 资金费率失败: {e}")
                logger.exception(e)
        
        logger.info(f"✅ 所有交易所资金费率检查完成")
    
    async def run(self):
        """
        启动资金费率监控器
        """
        if self.is_running:
            logger.warning("资金费率监控器已经在运行中")
            return
            
        self.is_running = True
        logger.info("🚀 启动资金费率监控器")
        
        try:
            # 初始化连接器
            await self.initialize()
            
            while self.is_running:
                await self.check_and_notify()
                
                # 等待下一次检查
                await asyncio.sleep(Config.FUNDING_RATE_CHECK_INTERVAL)
                
        except Exception as e:
            logger.error(f"❌ 资金费率监控器运行失败: {e}")
        finally:
            self.is_running = False
            logger.info("🛑 资金费率监控器已停止")
    
    def stop(self):
        """
        停止资金费率监控器
        """
        self.is_running = False
        logger.info("⏹️  正在停止资金费率监控器...")
    
    async def close(self):
        """
        关闭所有连接器
        """
        for connector in self.connectors.values():
            try:
                await connector.close()
            except Exception as e:
                logger.error(f"❌ 关闭连接器失败: {e}")
