# Coin Monitor 架构文档

## 系统架构概览

Coin Monitor 是一个全球多交易所资金流监控系统，采用模块化设计，支持实时监控和分析。

## 核心模块

### 1. 连接器层 (Connectors)

**位置**: `src/connectors/`

**职责**: 统一封装各交易所API，提供标准化数据接口

**主要类**:
- `ExchangeConnector` (基类): 定义统一接口
- `BinanceConnector`: Binance交易所连接
- `OKXConnector`: OKX交易所连接
- `BybitConnector`: Bybit交易所连接
- `CoinbaseConnector`: Coinbase交易所连接

**设计模式**: 策略模式 + 模板方法模式

### 2. 数据处理器 (Processors)

**位置**: `src/processors/`

**职责**: 数据标准化和转换

**主要功能**:
- 将不同交易所的K线数据转换为统一的 `StandardCandle` 格式
- 计算USDT计价的主买/主卖量
- 计算净资金流 (Net Flow = Taker Buy - Taker Sell)
- 时间戳对齐和排序

### 3. 分析器层 (Analyzers)

**位置**: `src/analyzers/`

**职责**: 多维度市场分析

**核心分析器**:

1. **TakerFlowAnalyzer**: 资金流分析
   - 计算累积净资金流（50分钟窗口）
   - 计算买卖比 (Buy/Sell Ratio)
   - 提取价格结构（支撑/阻力/ATR）

2. **MultiPlatformAnalyzer**: 多平台信号聚合
   - 市场共识判断（强力看涨/看跌/震荡）
   - 信号识别（A+/A/B+/C级）

3. **EarlyPumpAnalyzer**: 早期拉盘检测
   - 1分钟主力拉盘检测
   - 自适应波动率阈值
   - 多时间框架共振确认

4. **SteadyGrowthAnalyzer**: 稳步上涨趋势识别
   - 15分钟稳步上涨趋势识别
   - 均线多头排列确认

5. **PanicDumpAnalyzer**: 恐慌出货检测
   - 主力暴力出货检测
   - 恐慌抛售识别

6. **WhaleWatcher**: 巨鲸监控
   - 大额交易监控（默认$200k+）
   - 实时捕捉巨鲸动向

7. **VolumeSpikeAnalyzer**: 成交量暴增检测
   - 异常放量识别

8. **SpotFuturesAnalyzer**: 现货-合约联动分析
   - 现货-合约价差分析
   - 套利机会识别

### 4. 策略层 (Strategies)

**位置**: `src/strategies/`

**职责**: 交易策略生成

**EntryExitStrategy**:
- 入场/出场逻辑
- 多时间框架趋势确认（5m/1h）
- 动态止损/止盈计算（基于ATR）
- 共识连续性追踪
- 仓位大小计算

### 5. 服务层 (Services)

**位置**: `src/services/`

**职责**: 通知和实时监控

**NotificationService**:
- 钉钉机器人推送（支持加签）
- 企业微信推送
- 分级推送策略（A+/A立即，B级汇总）
- 消息格式化（Markdown）

**RealtimeMonitor**:
- WebSocket实时监控
- 实时拉盘警报
- 连接健康检查
- 指数退避重连

### 6. 存储层 (Storage)

**位置**: `src/storage/`

**职责**: 数据持久化

**Persistence**:
- SQLite数据库存储
- 信号记录表 (`signals`)
- 策略建议表 (`recommendations`)
- JSON格式存储平台指标

### 7. 工具层 (Utils)

**位置**: `src/utils/`

**职责**: 通用工具函数

**主要模块**:
- `indicators.py`: 技术指标计算（ATR、MA、趋势判断）
- `position_manager.py`: 仓位管理（风险控制）
- `market_regime.py`: 市场环境判断（牛市/熊市/震荡）
- `logger.py`: 日志配置
- `discovery.py`: 币种发现
- `dataframe_helpers.py`: DataFrame辅助函数

### 8. 核心模块 (Core)

**位置**: `src/core/`

**职责**: 核心抽象和上下文管理

**AnalysisContext**:
- 统一管理所有分析器和服务引用
- 解决函数参数过多的问题
- 提高代码可维护性

**SymbolProcessor**:
- 模块化的符号处理函数
- `fetch_symbol_data()`: 数据获取
- `analyze_platform()`: 单平台分析
- `aggregate_signals()`: 信号聚合
- `generate_recommendations()`: 策略建议

## 数据流

```
1. 币种发现
   └─▶ 扫描交易所，过滤24h成交额 > 阈值

2. 数据获取（并发）
   ├─▶ K线数据（1m/5m/15m/1h）
   ├─▶ 交易记录（用于巨鲸监控）
   └─▶ 24h Ticker（成交额）

3. 数据处理
   └─▶ 标准化 → DataFrame

4. 多维度分析（并行）
   ├─▶ 资金流分析 (TakerFlowAnalyzer)
   ├─▶ 早期拉盘检测 (EarlyPumpAnalyzer)
   ├─▶ 稳步上涨检测 (SteadyGrowthAnalyzer)
   ├─▶ 恐慌出货检测 (PanicDumpAnalyzer)
   ├─▶ 成交量暴增 (VolumeSpikeAnalyzer)
   └─▶ 巨鲸监控 (WhaleWatcher)

5. 多平台聚合
   └─▶ 市场共识 + 信号识别 (MultiPlatformAnalyzer)

6. 策略评估
   └─▶ 入场/出场建议 (EntryExitStrategy)

7. 输出
   ├─▶ 日志输出
   ├─▶ 通知推送（钉钉/企业微信）
   └─▶ 数据持久化（SQLite）
```

## 设计模式

1. **策略模式**: 不同交易所使用不同的连接器实现
2. **模板方法模式**: 基类定义流程，子类实现具体细节
3. **观察者模式**: 信号触发通知（可扩展）
4. **工厂模式**: 分析器和服务创建

## 性能优化

1. **缓存机制**: 市场环境判断使用5分钟缓存
2. **并发处理**: 使用 asyncio 实现异步并发
3. **DataFrame优化**: 减少重复的索引访问
4. **连接管理**: WebSocket使用指数退避重连

## 扩展性

系统采用模块化设计，易于扩展：

1. **添加新交易所**: 实现 `ExchangeConnector` 接口
2. **添加新分析器**: 创建新的分析器类
3. **添加新策略**: 扩展 `EntryExitStrategy`
4. **添加新通知渠道**: 扩展 `NotificationService`

## 配置管理

所有配置集中在 `src/config.py`，支持：
- 文件配置（默认值）
- 环境变量（优先）
- 类型验证

## 测试

测试框架使用 pytest，包含：
- 单元测试 (`tests/test_*.py`)
- 集成测试（标记为 `@pytest.mark.integration`）
- 测试配置 (`pytest.ini`)

## 日志

使用 loguru 进行日志管理：
- 结构化日志输出
- 日志轮转和压缩
- 不同级别的日志（DEBUG/INFO/WARNING/ERROR/CRITICAL）
