from typing import List, Dict, Any
from src.config import Config

class WhaleWatcher:
    """
    Monitors large transactions.
    """
    def __init__(self, threshold: float = Config.WHALE_THRESHOLD):
        self.threshold = threshold

    def check_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters trades exceeding the threshold.
        """
        whales = []
        for t in trades:
            # Trade format depends on Connector, usually: {'amount': ..., 'price': ..., 'cost': ...}
            # CCXT trades have 'cost' (amount * price).
            cost = t.get('cost')
            if cost is None and 'amount' in t and 'price' in t:
                cost = float(t['amount']) * float(t['price'])
            
            if cost and cost >= self.threshold:
                whales.append({
                    'timestamp': t['timestamp'],
                    'side': t['side'],
                    'amount': t['amount'],
                    'price': t['price'],
                    'cost': cost,
                    'symbol': t['symbol']
                })
        return whales
