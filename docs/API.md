# Coin Monitor API 文档

## 核心类和方法

### AnalysisContext

**位置**: `src/core/context.py`

**描述**: 统一管理所有分析器和服务引用的上下文对象

**属性**:
- `connectors`: Dict[str, ExchangeConnector] - 连接器字典
- `taker_analyzer`: TakerFlowAnalyzer - 资金流分析器
- `multi_analyzer`: MultiPlatformAnalyzer - 多平台分析器
- `whale_watcher`: WhaleWatcher - 巨鲸监控器
- `vol_spike_analyzer`: VolumeSpikeAnalyzer - 成交量分析器
- `early_pump_analyzer`: EarlyPumpAnalyzer - 早期拉盘分析器
- `panic_dump_analyzer`: PanicDumpAnalyzer - 恐慌出货分析器
- `steady_growth_analyzer`: SteadyGrowthAnalyzer - 稳步上涨分析器
- `sf_analyzer`: SpotFuturesAnalyzer - 现货合约分析器
- `strategy`: EntryExitStrategy - 交易策略
- `notification_service`: Optional[NotificationService] - 通知服务
- `persistence`: Optional[Persistence] - 持久化服务
- `market_regime`: str - 市场环境

### TakerFlowAnalyzer

**位置**: `src/analyzers/taker_flow.py`

**方法**:
- `analyze(df: pd.DataFrame) -> Dict[str, Any]`
  - 分析资金流趋势
  - 返回: 包含累积净资金流、买卖比、价格结构等

### MultiPlatformAnalyzer

**位置**: `src/analyzers/multi_platform.py`

**方法**:
- `get_market_consensus(platform_metrics: Dict) -> str`
  - 获取市场共识
  - 返回: 共识描述字符串
  
- `analyze_signals(platform_metrics: Dict, symbol: str, df_5m: Optional[pd.DataFrame], df_1h: Optional[pd.DataFrame]) -> List[Dict]`
  - 分析多平台信号
  - 返回: 信号列表

### MarketRegimeDetector

**位置**: `src/utils/market_regime.py`

**方法**:
- `analyze(btc_df: pd.DataFrame, force_refresh: bool = False) -> Dict[str, str]`
  - 分析市场环境
  - 支持缓存机制（默认5分钟）
  - 返回: {'regime': 'BULL'|'BEAR'|'NEUTRAL', 'desc': str}
  
- `is_cache_valid() -> bool`
  - 检查缓存是否有效
  
- `get_cached_result() -> Optional[Dict[str, str]]`
  - 获取缓存的结果

## 工具函数

### DataFrame 辅助函数

**位置**: `src/utils/dataframe_helpers.py`

**函数**:
- `get_latest_values(df: pd.DataFrame, n: int = 2) -> Tuple[pd.Series, ...]`
  - 获取最后n行数据，避免重复调用 `.iloc[-1]`
  
- `get_latest_value(df: pd.DataFrame, column: str, default: Any = None) -> Any`
  - 获取最后一行的指定列值
  
- `get_latest_n_values(df: pd.DataFrame, column: str, n: int = 2) -> List[Any]`
  - 获取最后n行的指定列值列表

## 配置

### Config 类

**位置**: `src/config.py`

**主要配置项**:
- `SYMBOL`: 默认监控币种
- `ENABLE_MULTI_SYMBOL`: 是否启用多币种扫描
- `TIMEFRAME`: K线时间周期
- `MARKET_TYPE`: 市场类型 ('spot' 或 'future')
- `MIN_24H_QUOTE_VOLUME`: 24小时成交额过滤阈值
- `ENABLE_DINGTALK`: 是否启用钉钉通知
- `ENABLE_WECHAT`: 是否启用企业微信通知
- `WHALE_THRESHOLD`: 巨鲸监控阈值

**环境变量支持**:
- `ENABLE_DINGTALK`: 钉钉通知开关
- `DINGTALK_WEBHOOK`: 钉钉Webhook URL
- `DINGTALK_SECRET`: 钉钉加签密钥
- `ENABLE_WECHAT`: 企业微信通知开关
- `WECHAT_WEBHOOK`: 企业微信Webhook URL

## 异常类

**位置**: `src/core/exceptions.py`

**异常类**:
- `CoinMonitorError`: 基础异常类
- `ExchangeConnectionError`: 交易所连接错误
- `DataFetchError`: 数据获取错误
- `AnalysisError`: 分析错误
- `ConfigurationError`: 配置错误
- `NotificationError`: 通知错误
