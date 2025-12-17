import time
import hmac
import hashlib
import base64
import urllib.parse
import aiohttp
from typing import Dict, Optional
from datetime import datetime
from src.utils.logger import logger
from src.config import Config


class NotificationService:
    """
    通知服务：支持钉钉和企业微信推送
    """
    
    def __init__(self):
        self.dingtalk_webhook = Config.DINGTALK_WEBHOOK
        self.dingtalk_secret = Config.DINGTALK_SECRET
        self.wechat_webhook = Config.WECHAT_WEBHOOK
        self.enable_dingtalk = Config.ENABLE_DINGTALK
        self.enable_wechat = Config.ENABLE_WECHAT
        self.notify_grades = Config.NOTIFY_GRADES
        
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
    
    async def send_dingtalk(self, message: str, at_all: bool = False) -> bool:
        """
        发送钉钉消息
        """
        if not self.enable_dingtalk or not self.dingtalk_webhook:
            return False
        
        try:
            # 构建 URL（含加签）
            timestamp = int(time.time() * 1000)
            url = self.dingtalk_webhook
            
            if self.dingtalk_secret:
                sign = self._generate_dingtalk_sign(timestamp, self.dingtalk_secret)
                url = f"{url}&timestamp={timestamp}&sign={sign}"
            
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
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    result = await resp.json()
                    if result.get('errcode') == 0:
                        logger.info("✅ 钉钉消息发送成功")
                        return True
                    else:
                        logger.error(f"❌ 钉钉消息发送失败: {result}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ 钉钉推送异常: {e}")
            return False
    
    async def send_wechat(self, message: str) -> bool:
        """
        发送企业微信消息
        """
        if not self.enable_wechat or not self.wechat_webhook:
            return False
        
        try:
            # 构建消息体
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": message
                }
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(self.wechat_webhook, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    result = await resp.json()
                    if result.get('errcode') == 0:
                        logger.info("✅ 企业微信消息发送成功")
                        return True
                    else:
                        logger.error(f"❌ 企业微信消息发送失败: {result}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ 企业微信推送异常: {e}")
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
        
        # 获取市场共识
        from src.analyzers.multi_platform import MultiPlatformAnalyzer
        analyzer = MultiPlatformAnalyzer()
        consensus = analyzer.get_market_consensus(platform_metrics)
        
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

**市场共识**: {consensus}

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
    
    async def send_whale_alert(self, whale_data: Dict, symbol: str, exchange: str):
        """
        发送巨鲸交易警报
        """
        if not Config.ENABLE_WHALE_NOTIFY:
            return
        
        # 检查是否达到推送阈值
        if whale_data['cost'] < Config.WHALE_NOTIFY_THRESHOLD:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        side = whale_data['side'].upper()
        side_cn = "买入" if side == 'BUY' else "卖出"
        emoji = "📈" if side == 'BUY' else "📉"
        
        # 构建消息
        message = f"""### 🐳 巨鲸交易警报

**币种**: **{symbol}**
**交易所**: {exchange.upper()}
**方向**: {emoji} **{side_cn}**
**金额**: <font color='{"green" if side == "BUY" else "red"}'>**${whale_data['cost']:,.0f}**</font>
**价格**: ${whale_data['price']:,.4f}
**时间**: {timestamp}

---

**分析**:
{'🟢 大资金主动买入，可能预示上涨趋势' if side == 'BUY' else '🔴 大资金主动卖出，可能预示下跌趋势'}

---
<font color='comment'>*实时巨鲸监控 - 阈值: ${Config.WHALE_NOTIFY_THRESHOLD:,.0f}*</font>
"""
        
        logger.info(f"📢 触发巨鲸警报，推送通知...")
        
        # 钉钉推送（不 @所有人）
        if self.enable_dingtalk:
            await self.send_dingtalk(message, at_all=False)
        
        # 企业微信推送
        if self.enable_wechat:
            await self.send_wechat(message)
    
    async def send_consensus_alert(self, consensus: str, platform_metrics: Dict, symbol: str):
        """
        发送市场共识警报（强力看涨/看跌）
        """
        if not Config.ENABLE_CONSENSUS_NOTIFY:
            return
        
        # 只推送强力看涨和强力看跌
        if "强力看涨" not in consensus and "强力看跌" not in consensus:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 判断方向
        is_bullish = "看涨" in consensus
        emoji = "🚀" if is_bullish else "⚠️"
        color = "green" if is_bullish else "red"
        
        # 构建平台资金流向
        flow_lines = []
        for name, metrics in platform_metrics.items():
            flow = metrics.get('cumulative_net_flow', 0)
            flow_k = flow / 1000
            flow_emoji = "📈" if flow > 0 else "📉"
            flow_color = "green" if flow > 0 else "red"
            flow_lines.append(f"- {flow_emoji} **{name.upper()}**: <font color='{flow_color}'>{flow_k:+.0f}k USDT</font>")
        
        # 构建消息
        message = f"""### {emoji} 市场共识警报

**币种**: **{symbol}**
**共识**: <font color='{color}'>**{consensus}**</font>
**触发时间**: {timestamp}

---

**平台资金流向** (过去50分钟):
{chr(10).join(flow_lines)}

---

**分析**:
{'🟢 全平台一致看多，主力资金同步建仓，市场情绪高度一致' if is_bullish else '🔴 全平台一致看空，主力资金同步撤离，市场情绪极度悲观'}

**建议**:
{'📈 适合追涨或加仓，止损设置在关键支撑位' if is_bullish else '📉 建议观望或减仓，等待市场企稳信号'}

---
<font color='comment'>*全平台共识监控*</font>
"""
        
        logger.info(f"📢 触发市场共识警报 ({consensus})，推送通知...")
        
        # 钉钉推送（@所有人）
        if self.enable_dingtalk:
            await self.send_dingtalk(message, at_all=True)
        
        # 企业微信推送
        if self.enable_wechat:
            await self.send_wechat(message)
    
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
        text = f"""### 🎯 策略建议

**币种**: **{symbol}**
**动作**: **{action} {side}**
**价格**: ${price:.4f}
**止损**: {('未设置' if sl is None else f'${sl:.4f}')}
**止盈**: {('未设置' if tp is None else f'${tp:.4f}')}
**理由**: {reason}

---

**平台资金流向**:
{chr(10).join(lines)}
"""
        if self.enable_dingtalk:
            await self.send_dingtalk(text, at_all=False)
        if self.enable_wechat:
            await self.send_wechat(text)
