import pandas as pd
from src.utils.logger import logger

class TakerFlowAnalyzer:
    """
    Analyzes Taker Flow trends.
    """
    def __init__(self, window: int = 50):
        self.window = window

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Calculates Long-Term Net Flow and interpretation.
        """
        if df.empty or 'net_flow_usdt' not in df.columns:
            return {'net_flow': 0.0, 'trend': 'Neutral'}

        # Calculate Cumulative Net Flow for the last N periods
        # Assuming df is sorted by time and covers the window
        recent_df = df.tail(self.window)
        # Drop rows with NaN in net_flow_usdt
        valid_df = recent_df.dropna(subset=['net_flow_usdt'])
        
        cumulative_net_flow = valid_df['net_flow_usdt'].sum()

        # Buy/Sell Ratio
        total_buy = valid_df['taker_buy_usdt'].sum()
        total_sell = valid_df['taker_sell_usdt'].sum()
        if total_sell > 0:
            ratio = total_buy / total_sell
        else:
            ratio = float('inf') if total_buy > 0 else 0.0
            
        return {
            'cumulative_net_flow': cumulative_net_flow,
            'buy_sell_ratio': ratio
        }
