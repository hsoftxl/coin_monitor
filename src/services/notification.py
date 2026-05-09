import time
import hmac
import hashlib
import base64
import urllib.parse
import aiohttp
from typing import Dict, Optional, TYPE_CHECKING
from datetime import datetime
from src.utils.logger import logger
from src.config import Config

# 延迟导入异常类，避免循环导入
if TYPE_CHECKING:
    from src.core.exceptions import NotificationError
else:
    NotificationError = Exception  # 运行时占位符


class NotificationService:
    """
    通知服务：支持钉钉和企业微信推送
    """
    
    def __init__(self):
        # 主通道配置
        self.dingtalk_webhook = Config.DINGTALK_WEBHOOK
        self.dingtalk_secret = Config.DINGTALK_SECRET
        self.wechat_webhook = Config.WECHAT_WEBHOOK
        self.enable_dingtalk = Config.ENABLE_DINGTALK
        self.enable_wechat = Config.ENABLE_WECHAT
        self.notify_grades = Config.NOTIFY_GRADES
        
        # 拉盘专用通道配置
        self.enable_pump_channel = Config.ENABLE_PUMP_CHANNEL
        self.pump_dingtalk_webhook = Config.PUMP_DINGTALK_WEBHOOK
        self.pump_dingtalk_secret = Config.PUMP_DINGTALK_SECRET
        self.pump_wechat_webhook = Config.PUMP_WECHAT_WEBHOOK
        

        
        # 资金费率专用通道配置
        self.enable_funding_channel = Config.ENABLE_FUNDING_CHANNEL
        self.funding_dingtalk_webhook = Config.FUNDING_DINGTALK_WEBHOOK
        self.funding_dingtalk_secret = Config.FUNDING_DINGTALK_SECRET
        self.funding_wechat_webhook = Config.FUNDING_WECHAT_WEBHOOK
        
        # 消息队列（用于 B 级信号汇总）
        self.pending_b_signals = []
        self.last_b_summary_time = time.time()
    
    def _generate_dingtalk_sign(self, timestamp: int, secret: str) -> str:
        """
        生成钉钉加签
        """
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign
    
    async def send_dingtalk(self, message: str, at_all: bool = False, webhook: str = None, secret: str = None) -> bool:
        """
        发送钉钉消息
        
        Args:
            message: 消息内容
            at_all: 是否@所有人
            webhook: 自定义webhook URL（如果为None，使用默认webhook）
            secret: 自定义secret（如果为None，使用默认secret）
        """
        # 使用自定义webhook或默认webhook
        target_webhook = webhook or self.dingtalk_webhook
        target_secret = secret or self.dingtalk_secret
        
        if not target_webhook:
            logger.debug(f"❌ 钉钉推送失败: webhook为空")
            return False
        
        logger.debug(f"📤 准备发送钉钉消息: webhook={target_webhook[:30]}..., at_all={at_all}")
        
        try:
            # 构建 URL（含加签）
            timestamp = int(time.time() * 1000)
            url = target_webhook
            
            if target_secret:
                sign = self._generate_dingtalk_sign(timestamp, target_secret)
                url = f"{url}&timestamp={timestamp}&sign={sign}"
                logger.debug(f"🔐 钉钉URL已加签")
            else:
                logger.debug(f"🔓 钉钉URL未加签")
            
            # 构建消息体
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "资金流监控报警",
                    "text": message
                }
            }
            
            if at_all:
                payload["at"] = {"isAtAll": True}
                logger.debug(f"🔔 钉钉消息将@所有人")
            
            # 发送请求
            logger.debug(f"📡 发送钉钉HTTP请求...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    logger.debug(f"📊 钉钉响应状态码: {resp.status}")
                    result = await resp.json()
                    logger.debug(f"📝 钉钉响应内容: {result}")
                    if result.get('errcode') == 0:
                        logger.info("✅ 钉钉消息发送成功")
                        return True
                    else:
                        logger.error(f"❌ 钉钉消息发送失败: {result}")
                        return False
        
        except (aiohttp.ClientError, ValueError, KeyError) as e:
            logger.error(f"❌ 钉钉推送异常: {e}")
            logger.exception(e)
            # 只记录日志，不抛出异常，防止主程序崩溃
            return False
        except Exception as e:
            logger.error(f"❌ 钉钉推送未知异常: {e}")
            logger.exception(e)
            # 只记录日志，不抛出异常，防止主程序崩溃
            return False
    
    async def send_wechat(self, message: str, webhook: str = None) -> bool:
        """
        发送企业微信消息
        
        Args:
            message: 消息内容
            webhook: 自定义webhook URL（如果为None，使用默认webhook）
        """
        # 使用自定义webhook或默认webhook
        target_webhook = webhook or self.wechat_webhook
        
        if not target_webhook:
            logger.debug(f"❌ 企业微信推送失败: webhook为空")
            return False
        
        logger.debug(f"📤 准备发送企业微信消息: webhook={target_webhook[:30]}...")
        
        try:
            # 构建消息体
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": message
                }
            }
            logger.debug(f"📝 企业微信消息体构建完成")
            
            # 发送请求
            logger.debug(f"📡 发送企业微信HTTP请求...")
            async with aiohttp.ClientSession() as session:
                async with session.post(target_webhook, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    logger.debug(f"📊 企业微信响应状态码: {resp.status}")
                    result = await resp.json()
                    logger.debug(f"📝 企业微信响应内容: {result}")
                    if result.get('errcode') == 0:
                        logger.info("✅ 企业微信消息发送成功")
                        return True
                    else:
                        logger.error(f"❌ 企业微信消息发送失败: {result}")
                        return False
        
        except (aiohttp.ClientError, ValueError, KeyError) as e:
            logger.error(f"❌ 企业微信推送异常: {e}")
            logger.exception(e)
            # 只记录日志，不抛出异常，防止主程序崩溃
            return False
        except Exception as e:
            logger.error(f"❌ 企业微信推送未知异常: {e}")
            logger.exception(e)
            # 只记录日志，不抛出异常，防止主程序崩溃
            return False
    
    def format_signal_message(self, signal: Dict, platform_metrics: Dict, symbol: str) -> str:
        """
        格式化信号消息为 Markdown
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建平台资金流向
        flow_lines = []
        for name, metrics in platform_metrics.items():
            flow = metrics.get('cumulative_net_flow', 0)
            flow_k = flow / 1000
            emoji = "📈" if flow > 0 else "📉"
            color_tag = "green" if flow > 0 else "red"
            flow_lines.append(f"- {emoji} **{name.upper()}**: <font color='{color_tag}'>{flow_k:+.0f}k USDT</font>")
        

        
        # 根据信号等级给出行动建议
        grade = signal.get('grade', 'C')
        if grade == 'A+':
            action = "🚀 **强烈建议**: 主力全平台建仓，适合追涨或加仓，止损设置在关键支撑位。"
        elif grade == 'A':
            action = "💎 **建议**: 机构资金流入，适合中长期持有，关注后续平台跟进。"
        elif grade == 'B':
            action = "⚠️ **观察**: 存在对冲行为，建议等待方向明确后再操作。"
        else:
            action = "🛑 **警惕**: 可能存在诱多陷阱，不建议追涨，已持仓考虑减仓。"
        
        # 构建 Markdown 消息
        message = f"""### 🚨 全球主力资金监控系统报警

**信号类型**: {signal['type']} 
**信号等级**: <font color='red'>**{grade}**</font>
**币种**: **{symbol}**
**触发时间**: {timestamp}

---

**平台资金流向** (过去50分钟):
{chr(10).join(flow_lines)}

---

**信号解读**: {signal['desc']}

{action}

---
<font color='comment'>*数据来源: Binance, OKX, Bybit, Coinbase*</font>
"""
        return message
    
    async def dispatch_signal(self, signal: Dict, platform_metrics: Dict, symbol: str):
        """
        根据信号等级路由推送
        """
        grade = signal.get('grade', 'C')
        
        # 只推送配置中指定等级的信号
        if grade not in self.notify_grades:
            logger.debug(f"信号等级 {grade} 不在推送列表中，跳过通知")
            return
        
        # 格式化消息
        message = self.format_signal_message(signal, platform_metrics, symbol)
        
        # A+/A 级信号：立即推送 + @所有人
        if grade in ['A+', 'A']:
            logger.info(f"📢 触发 {grade} 级信号，立即推送通知...")
            
            # 钉钉推送（@所有人）
            if self.enable_dingtalk:
                await self.send_dingtalk(message, at_all=True)
            
            # 企业微信推送
            if self.enable_wechat:
                await self.send_wechat(message)
        
        # B 级信号：加入待汇总队列
        elif grade == 'B':
            self.pending_b_signals.append({
                'signal': signal,
                'metrics': platform_metrics,
                'symbol': symbol,
                'timestamp': time.time()
            })
            logger.debug(f"B 级信号已加入汇总队列，当前队列长度: {len(self.pending_b_signals)}")
            
            # 每 30 分钟汇总一次
            if time.time() - self.last_b_summary_time > 1800:  # 1800秒 = 30分钟
                await self._send_b_summary()
        
        # C 级信号：仅记录日志
        else:
            logger.debug(f"C 级信号 [{symbol}] 仅记录日志，不推送通知")
    
    async def _send_b_summary(self):
        """
        发送 B 级信号汇总
        """
        if not self.pending_b_signals:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建汇总消息
        summary_lines = [f"### 📊 B级信号汇总报告\n**汇总时间**: {timestamp}\n**信号数量**: {len(self.pending_b_signals)}\n\n---\n"]
        
        for item in self.pending_b_signals:
            signal = item['signal']
            symbol = item['symbol']
            summary_lines.append(f"- **{symbol}**: {signal['type']} - {signal['desc']}")
        
        summary_lines.append("\n---\n<font color='comment'>*30分钟汇总推送*</font>")
        
        message = "\n".join(summary_lines)
        
        # 推送汇总
        if self.enable_dingtalk:
            await self.send_dingtalk(message, at_all=False)
        
        if self.enable_wechat:
            await self.send_wechat(message)
        
        # 清空队列
        self.pending_b_signals = []
        self.last_b_summary_time = time.time()
        logger.info(f"✅ B 级信号汇总已发送")
    

    

    
    async def send_strategy_recommendation(self, recommendation: Dict, platform_metrics: Dict):
        if not Config.ENABLE_STRATEGY:
            return
        action = recommendation.get('action')
        if not action:
            return
        symbol = recommendation.get('symbol', 'UNKNOWN')
        side = recommendation.get('side')
        price = recommendation.get('price')
        sl = recommendation.get('stop_loss')
        tp = recommendation.get('take_profit')
        reason = recommendation.get('reason', '')
        lines = []
        for name, metrics in platform_metrics.items():
            flow = metrics.get('cumulative_net_flow', 0)
            k = flow / 1000
            color = 'green' if flow > 0 else 'red'
            lines.append(f"- {name.upper()}: <font color='{color}'>{k:+.0f}k USDT</font>")
        pos_notional = recommendation.get('notional_usd')
        pos_size = recommendation.get('size_base')
        # 生成币安地址（根据市场类型）
        binance_url = self._get_binance_url(symbol, lang="zh-CN")
        
        text = f"""### 🎯 策略建议

**币种**: **{symbol}**
**动作**: **{action} {side}**
**价格**: ${price:.4f}
**止损**: {('未设置' if sl is None else f'${sl:.4f}')}
**止盈**: {('未设置' if tp is None else f'${tp:.4f}')}
**理由**: {reason}
{"**建议仓位**: " + (f"{pos_size:.4f} 份基币 (~${pos_notional:,.0f})" if (pos_notional and pos_size) else "待风险参数计算") }
**币安地址**: [{symbol}]({binance_url})

---

**平台资金流向**:
{chr(10).join(lines)}
"""
        if self.enable_dingtalk:
            await self.send_dingtalk(text, at_all=False)
        if self.enable_wechat:
            await self.send_wechat(text)



    async def send_early_pump_alert(self, data: Dict, symbol: str):
        """
        发送主力拉盘初期警报 (A+级)
        优先发送到拉盘专用通道，如果没有配置专用通道则发送到主通道
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pct = data['pct_change']
        vol = data['vol_ratio']
        buy_ratio = data['buy_ratio'] * 100
        price = data['price']
        
        # 生成币安地址（根据市场类型）
        binance_url = self._get_binance_url(symbol, lang="zh-CN")
        
        message = f"""### 🚀 主力拉盘启动警报
        
**币种**: **{symbol}**
**1分钟涨幅**: <font color='red'>**+{pct:.2f}%**</font>
**瞬间量能**: <font color='red'>**{vol:.1f}x**</font> (vs 1h均值)
**主动买入**: <font color='red'>**{buy_ratio:.0f}%**</font> (强力扫货)
**当前价格**: ${price:,.4f}
**触发时间**: {timestamp}
{self._format_24h_vol(data.get('vol_24h', 0))}
**币安地址**: [{symbol}]({binance_url})

---

**分析**:
监控到主力资金在**第1分钟**极速抢筹，价格快速脱离成本区，建议关注！
{f'''**策略建议**:
**动作**: {data['strategy']['action']} (盈亏比 {data['strategy']['risk_reward']}:1)
**买入**: ${data['strategy']['entry']:.4f}
**止损**: ${data['strategy']['sl']:.4f}
**止盈**: ${data['strategy']['tp']:.4f}''' if 'strategy' in data else ''}

---
<font color='comment'>*Early Pump Detection*</font>
        """
        logger.critical(f"🚀 触发主力拉盘警报 [{symbol}]，立即推送！")
        
        # 优先发送到拉盘专用通道
        if self.enable_pump_channel:
            if self.pump_dingtalk_webhook:
                await self.send_dingtalk(
                    message, 
                    at_all=True, 
                    webhook=self.pump_dingtalk_webhook,
                    secret=self.pump_dingtalk_secret
                )
            if self.pump_wechat_webhook:
                await self.send_wechat(message, webhook=self.pump_wechat_webhook)
        else:
            # 如果没有配置专用通道，发送到主通道
            if self.enable_dingtalk:
                await self.send_dingtalk(message, at_all=True)
            if self.enable_wechat:
                await self.send_wechat(message)

    async def send_panic_dump_alert(self, data: Dict, symbol: str):
        """
        发送主力暴力出货警报 (Panic Dump)
        """
        if not (self.enable_dingtalk or self.enable_wechat):
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pct = data['pct_change'] # Positive value representing drop
        vol = data['vol_ratio']
        sell_ratio = data['sell_ratio'] * 100
        price = data['price']
        
        # 生成币安地址（根据市场类型）
        binance_url = self._get_binance_url(symbol, lang="zh-CN")
        
        message = f"""### 📉 主力暴力出货警报
        
**币种**: **{symbol}**
**1分钟跌幅**: <font color='green'>**-{pct:.2f}%**</font>
**瞬间量能**: <font color='green'>**{vol:.1f}x**</font> (vs 1h均值)
**主动卖出**: <font color='green'>**{sell_ratio:.0f}%**</font> (恐慌抛售)
**当前价格**: ${price:,.4f}
**触发时间**: {timestamp}
**币安地址**: [{symbol}]({binance_url})

---

**分析**:
监控到主力资金在**第1分钟**集中抛售，价格快速下杀，谨防踩踏风险！
{f'''
**策略建议**:
**动作**: {data['strategy']['action']} (盈亏比 {data['strategy']['risk_reward']}:1)
**卖出**: ${data['strategy']['entry']:.4f}
**止损**: ${data['strategy']['sl']:.4f}
**止盈**: ${data['strategy']['tp']:.4f}''' if 'strategy' in data else ''}

---
<font color='comment'>*Panic Dump Detection*</font>
"""
        logger.critical(f"📉 触发主力出货警报 [{symbol}]，立即推送！")
        
        if self.enable_dingtalk:
            await self.send_dingtalk(message, at_all=True)
            
        if self.enable_wechat:
            await self.send_wechat(message)

    async def send_realtime_pump_alert(self, data: Dict, is_strategy_learned: bool = False):
        """
        发送实时拉盘警报 (WebSocket 实时监控)
        优先发送到拉盘专用通道，如果没有配置专用通道则发送到主通道
        
        Args:
            data: 警报数据
            is_strategy_learned: 是否是策略学习后的信号
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        symbol = data['symbol']
        pct = data['change_pct']
        vol = data['volume']
        price = data['price']
        is_closed = data['is_closed']
        market_label = data.get('market_label', '现货')  # Default to spot if not provided
        
        status_emoji = "🔴" if is_closed else "⚡"
        status_text = "已收盘" if is_closed else "实时"
        
        # 添加策略学习标记
        strategy_tag = "【策略学习】" if is_strategy_learned else ""
        
        # 生成币安地址（根据市场类型）
        binance_url = self._get_binance_url(symbol, lang="zh-CN")
        
        message = f"""### 🚀 {strategy_tag}实时拉盘警报 {status_emoji}
        
**币种**: **{symbol}** [{market_label}]
**状态**: {status_text}
**实时涨幅**: <font color='red'>**+{pct:.2f}%**</font>
**成交额**: <font color='red'>**${vol:,.0f}**</font> USDT
**当前价格**: ${price:,.4f}
**触发时间**: {timestamp}
**币安地址**: [{symbol}]({binance_url})

---

**分析**:
WebSocket 实时监控捕获，币种出现短时快速拉升，建议关注！

---
<font color='comment'>*Realtime WebSocket Monitor - {market_label}*</font>
        """
        logger.info(f"📢 触发实时拉盘警报 [{symbol} {market_label}]，推送通知...")
        
        # 优先发送到拉盘专用通道
        if self.enable_pump_channel:
            if self.pump_dingtalk_webhook:
                await self.send_dingtalk(
                    message, 
                    at_all=True, 
                    webhook=self.pump_dingtalk_webhook,
                    secret=self.pump_dingtalk_secret
                )
            if self.pump_wechat_webhook:
                await self.send_wechat(message, webhook=self.pump_wechat_webhook)
        else:
            # 如果没有配置专用通道，发送到主通道
            if self.enable_dingtalk:
                await self.send_dingtalk(message, at_all=True)
            if self.enable_wechat:
                await self.send_wechat(message)



    def _get_binance_url(self, symbol: str, market_type: str = None, lang: str = "en") -> str:
        """
        根据市场类型和语言生成正确的Binance URL
        
        Args:
            symbol: 交易对符号 (如 "BTC/USDT" 或 "BTC/USDT:USDT")
            market_type: 市场类型: 'spot' (现货) 或 'future' (合约)，默认使用配置值
            lang: 语言: 'en' (英文) 或 'zh-CN' (中文)
        
        Returns:
            正确的Binance交易对URL
        """
        if market_type is None:
            market_type = Config.MARKET_TYPE
        
        # 处理符号格式：移除斜杠和冒号
        cleaned_symbol = symbol.split(':')[0]  # 移除 :USDT 后缀
        binance_symbol = cleaned_symbol.replace('/', '')  # 移除斜杠
        
        if market_type == "future":
            # 合约URL格式：https://www.binance.com/en/futures/ICPUSDT
            return f"https://www.binance.com/{lang}/futures/{binance_symbol}"
        else:
            # 现货URL格式：https://www.binance.com/zh-CN/trade/ICP_USDT
            binance_symbol_for_spot = cleaned_symbol.replace('/', '_')
            return f"https://www.binance.com/{lang}/trade/{binance_symbol_for_spot}"
    
    def _format_24h_vol(self, vol_24h: float) -> str:
        if not vol_24h:
            return ""
        if vol_24h >= 100000000: # 100M
             vol_str = f"${vol_24h/1000000:.1f}M"
        elif vol_24h >= 1000000: # 1M
             vol_str = f"${vol_24h/1000000:.2f}M"
        elif vol_24h >= 1000:
             vol_str = f"${vol_24h/1000:.0f}k"
        else:
             vol_str = f"${vol_24h:.0f}"
              
        return f"**24h成交额**: {vol_str}"
    
    async def send_funding_rate_alert(self, funding_rate_data: Dict, symbol: str, exchange: str):
        """
        发送资金费率警报
        优先发送到资金费率专用通道，如果没有配置专用通道则发送到主通道
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        funding_rate = funding_rate_data['funding_rate'] * 100  # 转换为百分比
        next_funding_time = funding_rate_data.get('next_funding_time')
        price = funding_rate_data.get('price')
        
        logger.debug(f"📝 开始处理资金费率警报: {symbol}@{exchange}, 费率: {funding_rate:.4f}%, 阈值: {Config.FUNDING_RATE_THRESHOLD}%")
        
        # 处理价格可能为None或非数字的情况
        try:
            price_formatted = f"${float(price):,.4f}" if price is not None else "暂无数据"
        except (TypeError, ValueError):
            price_formatted = "暂无数据"
        
        # 生成币安地址（根据市场类型）
        binance_url = self._get_binance_url(symbol, lang="zh-CN")
        
        # 根据资金费率的正负值，生成不同的分析和建议内容
        if funding_rate > 0:
            # 正资金费率：多头支付费用给空头
            analysis = "资金费率大幅偏离正常值，表明市场情绪极度失衡。高资金费率意味着多头支付高额费用给空头，可能预示短期市场反转或持续极端行情。"
            suggestions = "- 多头谨慎追涨，注意回调风险\n- 空头可以考虑开仓或持有仓位\n- 关注资金费率变化趋势，可能预示市场转折点"
            rate_color = "red"
        else:
            # 负资金费率：空头支付费用给多头
            analysis = "资金费率大幅偏离正常值，表明市场情绪极度失衡。低资金费率意味着空头支付费用给多头，可能预示市场情绪转向看涨。"
            suggestions = "- 空头谨慎做空，注意反弹风险\n- 多头可以考虑开仓或持有仓位\n- 关注资金费率变化趋势，可能预示市场转折点"
            rate_color = "green"
        
        message = f"""### ⚡ 资金费率异常警报
        
**币种**: **{symbol}** [{exchange.upper()}]
**资金费率**: <font color='{rate_color}'>**{funding_rate:.4f}%**</font>
**触发阈值**: {Config.FUNDING_RATE_THRESHOLD}%
**当前价格**: {price_formatted}
**触发时间**: {timestamp}
**币安地址**: [{symbol}]({binance_url})
        
---
        
**分析**:
{analysis}
        
**建议**:
{suggestions}
        
---
<font color='comment'>*实时资金费率监控*</font>
        """
        logger.info(f"⚡ 触发资金费率警报 [{symbol}]，推送通知...")
        
        # 优先发送到资金费率专用通道
        if self.enable_funding_channel:
            logger.debug(f"🔗 启用资金费率专用通道，dingtalk: {bool(self.funding_dingtalk_webhook)}, wechat: {bool(self.funding_wechat_webhook)}")
            if self.funding_dingtalk_webhook:
                logger.debug(f"📤 通过资金费率专用钉钉通道发送: {self.funding_dingtalk_webhook[:30]}...")
                result = await self.send_dingtalk(
                    message, 
                    at_all=True, 
                    webhook=self.funding_dingtalk_webhook,
                    secret=self.funding_dingtalk_secret
                )
                logger.debug(f"✅ 资金费率专用钉钉通道发送结果: {result}")
            if self.funding_wechat_webhook:
                logger.debug(f"📤 通过资金费率专用微信通道发送: {self.funding_wechat_webhook[:30]}...")
                result = await self.send_wechat(message, webhook=self.funding_wechat_webhook)
                logger.debug(f"✅ 资金费率专用微信通道发送结果: {result}")
        else:
            # 如果没有配置专用通道，发送到主通道
            logger.debug(f"🔗 未启用资金费率专用通道，使用主通道")
            logger.debug(f"📤 主通道配置: dingtalk_enabled={self.enable_dingtalk}, wechat_enabled={self.enable_wechat}")
            if self.enable_dingtalk:
                logger.debug(f"📤 通过主钉钉通道发送")
                result = await self.send_dingtalk(message, at_all=True)
                logger.debug(f"✅ 主钉钉通道发送结果: {result}")
            if self.enable_wechat:
                logger.debug(f"📤 通过主微信通道发送")
                result = await self.send_wechat(message)
                logger.debug(f"✅ 主微信通道发送结果: {result}")
        logger.debug(f"📝 资金费率警报处理完成: {symbol}")

