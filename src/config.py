import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Symbol to monitor (Default if Multi-Symbol disabled)
    SYMBOL = "ETH/USDT"
    
    # Enable Multi-Symbol Discovery
    ENABLE_MULTI_SYMBOL = True
    
    # Timeframe for alignment (e.g., '15m', '1h')
    TIMEFRAME = "1m"
    
    # Whale Watch Threshold in USD
    WHALE_THRESHOLD = 200000.0  # $200k
    
    # Data Fetch Limits
    LIMIT_KLINE = 100
    LIMIT_TRADES = 1000
    
    # API Rates
    RATE_LIMIT_DELAY = 1.0 # seconds
    
    # Exchange Enabled Status
    EXCHANGES = {
        "binance": True,
        "okx": True,
        "bybit": True,
        "coinbase": True
    }

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Operations
    HEALTH_CHECK_INTERVAL = 60 # seconds
