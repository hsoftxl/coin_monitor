"""
Analysis Context - 统一管理所有分析器和服务引用
解决函数参数过多的问题，提高代码可维护性
"""

from __future__ import annotations  # 启用延迟类型评估，避免循环导入

from typing import Dict, Optional, TYPE_CHECKING, Any
from dataclasses import dataclass

from src.analyzers.taker_flow import TakerFlowAnalyzer
from src.analyzers.multi_platform import MultiPlatformAnalyzer
from src.analyzers.whale_watcher import WhaleWatcher
from src.analyzers.volume_spike import VolumeSpikeAnalyzer
from src.analyzers.early_pump import EarlyPumpAnalyzer
from src.analyzers.panic_dump import PanicDumpAnalyzer
from src.analyzers.steady_growth import SteadyGrowthAnalyzer
from src.analyzers.spot_futures_analyzer import SpotFuturesAnalyzer
from src.strategies.entry_exit import EntryExitStrategy

# 避免循环导入：使用 TYPE_CHECKING 和字符串类型提示
if TYPE_CHECKING:
    from src.services.notification import NotificationService
    from src.storage.persistence import Persistence
    from src.connectors.base import ExchangeConnector
else:
    # 运行时使用 Any 作为占位符
    NotificationService = Any
    Persistence = Any
    ExchangeConnector = Any


@dataclass
class AnalysisContext:
    """
    分析上下文对象，包含所有分析器和服务引用
    
    用于替代 process_symbol() 函数中的多个参数，
    提高代码可读性和可维护性。
    """
    # 连接器字典（使用字符串类型提示避免循环导入）
    connectors: Dict[str, Any]  # ExchangeConnector
    
    # 分析器
    taker_analyzer: TakerFlowAnalyzer
    multi_analyzer: MultiPlatformAnalyzer
    whale_watcher: WhaleWatcher
    vol_spike_analyzer: VolumeSpikeAnalyzer
    early_pump_analyzer: EarlyPumpAnalyzer
    panic_dump_analyzer: PanicDumpAnalyzer
    steady_growth_analyzer: SteadyGrowthAnalyzer
    sf_analyzer: SpotFuturesAnalyzer
    
    # 策略
    strategy: EntryExitStrategy
    
    # 服务（使用字符串类型提示避免循环导入）
    notification_service: Optional[Any] = None  # NotificationService
    persistence: Optional[Any] = None  # Persistence
    
    # 市场环境
    market_regime: str = 'NEUTRAL'
    
    def __post_init__(self):
        """验证上下文对象的有效性"""
        if not self.connectors:
            raise ValueError("connectors 不能为空")
        if not self.taker_analyzer:
            raise ValueError("taker_analyzer 不能为空")
        if not self.multi_analyzer:
            raise ValueError("multi_analyzer 不能为空")
