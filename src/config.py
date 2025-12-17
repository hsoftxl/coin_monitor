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
    
    # 24h quote volume filter (USD)
    MIN_24H_QUOTE_VOLUME = float(os.getenv("MIN_24H_QUOTE_VOLUME", "5000000"))
    EXCLUDED_SYMBOLS = [s.strip() for s in os.getenv("EXCLUDED_SYMBOLS", "USDC/USDT,XUSD/USDT,USDE/USDT").split(",") if s.strip()]
    ENABLE_STRATEGY = os.getenv("ENABLE_STRATEGY", "True").lower() == "true"
    STRATEGY_MIN_TOTAL_FLOW = float(os.getenv("STRATEGY_MIN_TOTAL_FLOW", "10000000"))
    STRATEGY_MIN_RATIO = float(os.getenv("STRATEGY_MIN_RATIO", "1.1"))
    
    # Exchange Enabled Status
    EXCHANGES = {
        "binance": True,
        "okx": True,
        "bybit": True,
        "coinbase": True
    }

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Notification Settings
    ENABLE_DINGTALK = os.getenv("ENABLE_DINGTALK", "True").lower() == "true"
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=36a7d64cdeaf611023d1ed25bd5f66f8df242632ae872b6769ce59c74235846b")
    DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "SEC10ac09242c4143447d588749090e334ba50e29f30b717c241c41ec86edfc6bfe")  # 可选：加签密钥
    
    ENABLE_WECHAT = os.getenv("ENABLE_WECHAT", "False").lower() == "true"
    WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK", "")
    
    # 通知等级阈值（只推送这些等级的信号）
    NOTIFY_GRADES = ["A+", "A"]
    
    # 巨鲸通知配置
    ENABLE_WHALE_NOTIFY = True
    WHALE_NOTIFY_THRESHOLD = 500000.0  # 只推送 >= $500k 的巨鲸交易
    
    # 市场共识通知
    ENABLE_CONSENSUS_NOTIFY = True  # 推送强力看涨/看跌共识
    
    # Operations
    HEALTH_CHECK_INTERVAL = 60 # seconds
