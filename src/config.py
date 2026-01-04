"""
配置文件 - 所有配置项都在此文件中直接设置
如需修改配置，直接编辑本文件即可，无需使用 .env 文件
"""

class Config:
    # ==================== 基础配置 ====================
    # 默认监控币种（当 ENABLE_MULTI_SYMBOL=False 时使用）
    SYMBOL = "ETH/USDT"
    
    # 是否启用多币种扫描
    ENABLE_MULTI_SYMBOL = True
    
    # K线时间周期 (优化为5m降低噪音)
    TIMEFRAME = "5m" 
    
    # 市场类型: 'spot' (现货) 或 'future' (U本位合约)
    MARKET_TYPE = "future"
    
    # Binance 合约类型 (当 MARKET_TYPE='future' 时有效)
    # 'swap': 永续合约 (USDT-M)
    BINANCE_FUTURE_TYPE = 'future' # ccxt property 'defaultType' 
    
    # 共振时间周期 (优化为1h提高可靠性)
    MTF_RES_TIMEFRAME = "1h"
    
    # 数据获取限制
    LIMIT_KLINE = 300    # K线数量
    LIMIT_TRADES = 1000  # 交易记录数量
    
    # API 请求延迟
    RATE_LIMIT_DELAY = 1.0  # 秒
    
    # 24小时成交额过滤（只监控成交额大于此值的币种）
    MIN_24H_QUOTE_VOLUME = 10000000  # 10M USDT
    
    # 排除的交易对
    EXCLUDED_SYMBOLS = ["USDC/USDT", "XUSD/USDT", "USDE/USDT"]
    
    # 日志级别
    LOG_LEVEL = "INFO"
    
    # ==================== 交易所配置 ====================
    EXCHANGES = {
        "binance": True,
        "okx": True,      # ✅ 开启多平台验证
        "bybit": False,
        "coinbase": False
    }
    
    # ==================== 通知配置 ====================
    # 钉钉通知
    ENABLE_DINGTALK = True  # 改这里：True启用 / False禁用
    DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=36a7d64cdeaf611023d1ed25bd5f66f8df242632ae872b6769ce59c74235846b"
    DINGTALK_SECRET = "SEC10ac09242c4143447d588749090e334ba50e29f30b717c241c41ec86edfc6bfe"
    
    # 企业微信通知
    ENABLE_WECHAT = False  # 改这里：True启用 / False禁用
    WECHAT_WEBHOOK = ""  # 填写你的企业微信机器人 Webhook
    
    # 通知等级阈值（只推送这些等级的信号）
    NOTIFY_GRADES = ["A+", "A"]
    
    # ==================== 巨鲸监控配置 ====================
    WHALE_THRESHOLD = 200000.0  # 监测阈值：$200k
    ENABLE_WHALE_NOTIFY = True  # 是否推送巨鲸通知
    WHALE_NOTIFY_THRESHOLD = 500000.0  # 推送阈值：>= $500k
    
    # ==================== 市场共识通知 ====================
    ENABLE_CONSENSUS_NOTIFY = False  # 推送强力看涨/看跌共识（已禁用）
    
    # ==================== Volume Spike 策略配置 ====================
    SPIKE_VOL_FACTOR = 3.0           # 成交量倍数（当前15m vs 5h均值）
    SPIKE_COOLDOWN_MINUTES = 30      # 冷却时间（分钟）
    SPIKE_MIN_PRICE_CHANGE = 0.5     # 最小涨幅 %
    
    # ==================== Early Pump 策略配置 ====================
    EARLY_PUMP_MIN_CHANGE = 1.0      # 最小涨幅 %（1分钟内）
    EARLY_PUMP_VOL_FACTOR = 5.0      # 成交量倍数（vs 1h均值）
    EARLY_PUMP_BUY_RATIO = 0.6       # 主动买入占比 > 60%
    EARLY_PUMP_COOLDOWN = 10         # 冷却时间（分钟）
    
    # ==================== 多时间框架配置 (Resonance) ====================
    ENABLE_MULTI_TIMEFRAME = True        # 启用多时间框架确认
    MTF_RES_TIMEFRAME = "15m"            # 共振确认周期
    MTF_MA_PERIOD = 20                   # 均线周期 (用于15m确认)
    
    # ==================== 波动率自适应配置 ====================
    ENABLE_ADAPTIVE_THRESHOLD = True      # 启用波动率自适应
    ATR_PERIOD = 14                       # ATR计算周期
    VOLATILITY_LOW_THRESHOLD = 3.0        # 低波动阈值 % (5m ATR)
    VOLATILITY_HIGH_THRESHOLD = 8.0       # 高波动阈值 % (5m ATR)
    PUMP_THRESHOLD_LOW_VOL = 1.5          # 低波动币种涨幅阈值
    PUMP_THRESHOLD_NORMAL_VOL = 2.0       # 正常波动涨幅阈值
    PUMP_THRESHOLD_HIGH_VOL = 3.0         # 高波动币种涨幅阈值
    
    # ==================== 现货-合约联动配置 ====================
    ENABLE_SPOT_FUTURES_CORRELATION = True  # 启用现货合约联动
    SF_DIVERGENCE_THRESHOLD = 0.5           # 合约领涨判定差值 %
    SF_CORRELATION_THRESHOLD = 0.3          # 相关性阈值 %
    
    # ==================== 实时 WebSocket 监控配置 ====================
    ENABLE_REALTIME_MONITOR = True         # 是否启用 WebSocket 实时监控
    
    # 市场类型配置
    ENABLE_SPOT_MARKET = True              # 监控现货市场
    ENABLE_FUTURES_MARKET = True           # 监控永续合约市场
    
    REALTIME_PUMP_THRESHOLD = 2.0          # 涨幅阈值 % (Raise to avoid noise)
    REALTIME_MIN_VOLUME = 100000           # 最小成交额 USDT
    REALTIME_BLACKLIST = ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT", "BUSDUSDT", "USDCUSDT"]
    
    # ==================== 交易策略配置 ====================
    ENABLE_STRATEGY = True
    STRATEGY_MIN_TOTAL_FLOW = 10000000     # 最小总资金流（USDT）
    STRATEGY_MIN_RATIO = 1.1               # 最小买卖比
    STRATEGY_MIN_INTERVAL_SEC = 900        # 最小信号间隔（秒）
    STRATEGY_ATR_SL_MULT = 1.5             # ATR止损倍数
    STRATEGY_ATR_TP_MULT = 2.0             # ATR止盈倍数
    STRATEGY_REQUIRE_MIDBAND = True        # 是否要求在中轨附近
    STRATEGY_MIN_CONSENSUS_BARS = 2        # 最小共识K线数
    STRATEGY_RISK_USD = 1000               # 单次风险金额
    STRATEGY_MAX_NOTIONAL_USD = 10000      # 最大名义金额
    
    # ==================== 数据持久化配置 ====================
    ENABLE_PERSISTENCE = True
    PERSIST_DB_PATH = "data/signals.db"
    
    # ==================== 运维配置 ====================
    HEALTH_CHECK_INTERVAL = 60  # 健康检查间隔（秒）
    
    # ==================== 仓位管理配置 (P0新增) ====================
    ACCOUNT_BALANCE = 10000.0          # 账户余额（USDT）- 必须设置为真实值
    RISK_PERCENTAGE = 2.0              # 单笔风险（账户%）
    MAX_POSITIONS = 5                  # 最大持仓数
    MAX_POSITION_NOTIONAL = 2000.0     # 单个仓位最大名义价值（USDT）
    
    # ==================== 做空配置 (P1新增) ====================
    ENABLE_SHORT_TRADING = True        # 启用做空策略
    SHORT_ONLY_IN_BEAR = True          # 仅在熊市做空（需要市场环境判断）
    
    # ==================== 多平台共识配置 (P0新增) ====================
    MIN_EXCHANGE_CONSENSUS = 2         # 至少需要N个交易所确认
    ENABLE_SINGLE_PLATFORM_TRAP_DETECTION = True  # 启用单平台诱多检测
