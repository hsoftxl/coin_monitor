import pandas as pd
from typing import List
from src.models import StandardCandle
from src.utils.logger import logger

class DataProcessor:
    """
    Standardizes candle data into USDT volumes and aligns timestamps.
    """
    
    @staticmethod
    def process_candles(candles: List[StandardCandle]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        
        data = []
        for c in candles:
            # 1. Determine Price for conversion
            # Use Close price as approximation for conversion if Quote volume not available
            price = c.close 
            
            # 2. Calculate USDT Volumes
            # If type is quote, it's already USDT.
            # If type is base, multiply by price.
            # If None, keep as None (NaN in DataFrame)
            
            taker_buy_usdt = None
            taker_sell_usdt = None
            
            if c.taker_buy_volume is not None:
                if c.volume_type == 'quote':
                    taker_buy_usdt = c.taker_buy_volume
                else:
                    taker_buy_usdt = c.taker_buy_volume * price
            
            if c.taker_sell_volume is not None:
                if c.volume_type == 'quote':
                    taker_sell_usdt = c.taker_sell_volume
                else:
                    taker_sell_usdt = c.taker_sell_volume * price
            
            # 3. Net Flow
            if taker_buy_usdt is not None and taker_sell_usdt is not None:
                net_flow = taker_buy_usdt - taker_sell_usdt
            else:
                net_flow = None
            
            data.append({
                'timestamp': pd.to_datetime(c.timestamp, unit='ms'),
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume,
                'taker_buy_usdt': taker_buy_usdt if taker_buy_usdt is not None else 0.0, # Or None? 
                # If we convert to DataFrame, None becomes NaN.
                # But 'taker_buy_usdt' type in previous version was float implies 0.0.
                # If we use NaN, we can filter easily.
                # Let's use None (NaN)
                'taker_buy_usdt': taker_buy_usdt,
                'taker_sell_usdt': taker_sell_usdt,
                'net_flow_usdt': net_flow,
                'exchange': c.exchange_id
            })
            
        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
        
        return df

    @staticmethod
    def align_dataframes(dfs: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Merges multiple exchange DataFrames on timestamp index.
        
        Args:
            dfs: List of DataFrames to align
            
        Returns:
            Merged DataFrame with aligned timestamps
            
        Note:
            Currently not used by MultiPlatformAnalyzer, but kept for future use.
            Each platform is analyzed independently and results are aggregated.
        """
        if not dfs:
            return pd.DataFrame()
        
        if len(dfs) == 1:
            return dfs[0]
        
        # Merge on timestamp index
        merged = dfs[0]
        for df in dfs[1:]:
            merged = merged.join(df, how='outer', rsuffix=f'_{len(merged.columns)}')
        
        return merged.sort_index()
