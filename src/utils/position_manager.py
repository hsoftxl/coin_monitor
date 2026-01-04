"""
仓位管理模块
负责计算仓位大小、风险控制、持仓限制等
"""

from typing import Dict, Optional
from src.config import Config
from src.utils.logger import logger


class PositionManager:
    """
    仓位管理器
    
    功能:
    1. 基于账户余额和风险百分比计算仓位
    2. 根据波动率调整仓位大小
    3. 控制最大持仓数量
    4. 限制单个仓位的名义价值
    """
    
    def __init__(self, account_balance: Optional[float] = None):
        """
        初始化仓位管理器
        
        Args:
            account_balance: 账户余额，默认使用配置中的值
        """
        self.account_balance = account_balance or Config.ACCOUNT_BALANCE
        self.positions: Dict[str, dict] = {}  # 当前持仓 {symbol: position_info}
        self.max_positions = Config.MAX_POSITIONS
        self.risk_per_trade = Config.RISK_PERCENTAGE / 100
        self.max_notional = Config.MAX_POSITION_NOTIONAL
        
        logger.info(f"📊 仓位管理器初始化: 账户={self.account_balance} USDT, "
                   f"风险={Config.RISK_PERCENTAGE}%, 最大持仓={self.max_positions}")
    
    def calculate_position_size(
        self, 
        symbol: str,
        entry_price: float, 
        stop_loss: float,
        volatility_level: str = 'NORMAL',
        take_profit: Optional[float] = None
    ) -> Dict:
        """
        计算仓位大小
        
        Args:
            symbol: 交易对符号
            entry_price: 入场价格
            stop_loss: 止损价格
            volatility_level: 波动率等级 ('LOW', 'NORMAL', 'HIGH')
            take_profit: 止盈价格（可选）
            
        Returns:
            包含仓位信息的字典:
            {
                'size': 仓位大小（币数）,
                'notional': 名义价值（USDT）,
                'risk_amount': 风险金额（USDT）,
                'pct_of_account': 占账户百分比,
                'risk_reward': 盈亏比（如果提供了take_profit）,
                'allowed': 是否允许开仓
            }
        """
        # 1. 计算每币风险
        risk_per_coin = abs(entry_price - stop_loss)
        
        if risk_per_coin <= 0:
            logger.warning(f"[{symbol}] 无效的止损价格: entry={entry_price}, sl={stop_loss}")
            return {'allowed': False, 'reason': 'Invalid stop loss'}
        
        # 2. 基础风险金额（账户的X%）
        risk_amount = self.account_balance * self.risk_per_trade
        
        # 3. 基础仓位大小 = 风险金额 / 每币风险
        base_size = risk_amount / risk_per_coin
        
        # 4. 根据波动率调整仓位
        volatility_multiplier = self._get_volatility_multiplier(volatility_level)
        adjusted_size = base_size * volatility_multiplier
        
        # 5. 计算名义价值
        notional_value = adjusted_size * entry_price
        
        # 6. 限制最大名义价值
        if notional_value > self.max_notional:
            adjusted_size = self.max_notional / entry_price
            notional_value = self.max_notional
            logger.debug(f"[{symbol}] 仓位因名义价值限制被调整: {notional_value:.2f} USDT")
        
        # 7. 计算实际风险和回报
        actual_risk = adjusted_size * risk_per_coin
        pct_of_account = (notional_value / self.account_balance) * 100
        
        # 8. 计算盈亏比
        risk_reward = None
        potential_profit = None
        if take_profit:
            profit_per_coin = abs(take_profit - entry_price)
            potential_profit = adjusted_size * profit_per_coin
            risk_reward = profit_per_coin / risk_per_coin if risk_per_coin > 0 else 0
        
        # 9. 检查是否允许开仓
        allowed, reason = self._check_can_open(symbol)
        
        result = {
            'symbol': symbol,
            'size': round(adjusted_size, 8),
            'notional': round(notional_value, 2),
            'risk_amount': round(actual_risk, 2),
            'potential_profit': round(potential_profit, 2) if potential_profit else None,
            'pct_of_account': round(pct_of_account, 2),
            'risk_reward': round(risk_reward, 2) if risk_reward else None,
            'volatility_level': volatility_level,
            'volatility_multiplier': volatility_multiplier,
            'allowed': allowed,
            'reason': reason if not allowed else 'OK'
        }
        
        return result
    
    def _get_volatility_multiplier(self, volatility_level: str) -> float:
        """
        根据波动率等级获取仓位倍数
        
        Args:
            volatility_level: 'LOW', 'NORMAL', 'HIGH'
            
        Returns:
            仓位倍数
        """
        multipliers = {
            'LOW': 1.2,    # 低波动，增加20%仓位
            'NORMAL': 1.0, # 正常波动，标准仓位
            'HIGH': 0.5    # 高波动，减半仓位
        }
        return multipliers.get(volatility_level, 1.0)
    
    def _check_can_open(self, symbol: str) -> tuple:
        """
        检查是否可以开新仓
        
        Args:
            symbol: 交易对符号
            
        Returns:
            (是否允许, 原因)
        """
        # 检查最大持仓数
        if len(self.positions) >= self.max_positions:
            if symbol not in self.positions:
                return False, f"达到最大持仓数 ({self.max_positions})"
        
        return True, "OK"
    
    def add_position(self, symbol: str, position_info: dict):
        """
        添加持仓记录
        
        Args:
            symbol: 交易对符号
            position_info: 仓位信息
        """
        self.positions[symbol] = position_info
        logger.info(f"📈 新增持仓: {symbol}, 数量={position_info.get('size')}, "
                   f"名义价值={position_info.get('notional')} USDT")
    
    def remove_position(self, symbol: str):
        """
        移除持仓记录
        
        Args:
            symbol: 交易对符号
        """
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            logger.info(f"📉 平仓: {symbol}, 名义价值={pos.get('notional')} USDT")
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """
        获取指定持仓信息
        
        Args:
            symbol: 交易对符号
            
        Returns:
            仓位信息字典或None
        """
        return self.positions.get(symbol)
    
    def get_total_exposure(self) -> float:
        """
        获取总敞口（所有持仓的名义价值总和）
        
        Returns:
            总敞口（USDT）
        """
        return sum(pos.get('notional', 0) for pos in self.positions.values())
    
    def get_total_risk(self) -> float:
        """
        获取总风险（所有持仓的风险金额总和）
        
        Returns:
            总风险（USDT）
        """
        return sum(pos.get('risk_amount', 0) for pos in self.positions.values())
    
    def get_position_count(self) -> int:
        """
        获取当前持仓数量
        
        Returns:
            持仓数量
        """
        return len(self.positions)
    
    def update_account_balance(self, new_balance: float):
        """
        更新账户余额
        
        Args:
            new_balance: 新的账户余额
        """
        old_balance = self.account_balance
        self.account_balance = new_balance
        logger.info(f"💰 账户余额更新: {old_balance:.2f} → {new_balance:.2f} USDT")
