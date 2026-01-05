import pandas as pd
from typing import Dict, Any
from src.utils.logger import logger

class TakerFlowAnalyzer:
    """
    Analyzes Taker Flow trends.
    """
    def __init__(self, window: int = 50):
        self.window = window

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
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
            
        # Extract Price Structure
        current_price = valid_df['close'].iloc[-1] if not valid_df.empty else 0.0
        # Support = Lowest Low in window
        support_low = valid_df['low'].min() if not valid_df.empty else 0.0
        # Resistance = Highest High in window
        resistance_high = valid_df['high'].max() if not valid_df.empty else 0.0
        
        prev_close = valid_df['close'].shift(1)
        tr1 = valid_df['high'] - valid_df['low']
        tr2 = (valid_df['high'] - prev_close).abs()
        tr3 = (valid_df['low'] - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.mean() if not true_range.empty else 0.0

        return {
            'cumulative_net_flow': cumulative_net_flow,
            'buy_sell_ratio': ratio,
            'current_price': current_price,
            'support_low': support_low,
            'resistance_high': resistance_high,
            'atr': atr
        }
    
    def analyze_df_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyzes a batch of data and adds the required columns to the DataFrame.
        """
        if df.empty:
            return df
        
        # Calculate taker buy and sell volumes in USDT
        df['taker_buy_usdt'] = df['taker_buy_quote_asset_volume']
        df['taker_sell_usdt'] = df['quote_volume'] - df['taker_buy_quote_asset_volume']
        df['net_flow_usdt'] = df['taker_buy_usdt'] - df['taker_sell_usdt']
        
        # Calculate cumulative net flow using rolling window
        df['cumulative_net_flow'] = df['net_flow_usdt'].rolling(window=self.window).sum()
        
        # Calculate buy/sell ratio
        df['buy_sell_ratio'] = df['taker_buy_usdt'] / df['taker_sell_usdt'].replace(0, float('inf'))
        df['buy_sell_ratio'] = df['buy_sell_ratio'].replace(float('inf'), 0)
        
        # Calculate ATR
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = (df['high'] - df['prev_close']).abs()
        df['tr3'] = (df['low'] - df['prev_close']).abs()
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=14).mean()
        
        # Drop temporary columns
        df.drop(['prev_close', 'tr1', 'tr2', 'tr3', 'true_range'], axis=1, inplace=True)
        
        return df
