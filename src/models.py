from dataclasses import dataclass
from typing import Optional

@dataclass
class StandardCandle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float  # Total Volume
    taker_buy_volume: Optional[float] = None
    taker_sell_volume: Optional[float] = None
    quote_volume: Optional[float] = None # Total Quote Volume
    volume_type: str = 'base' # 'base' or 'quote'
    exchange_id: str = ''
