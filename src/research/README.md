# Research 工具集

本目录包含了一套用于分析加密货币市场中做市商（Market Maker）行为特征的研究工具，能够生成做市商行为指纹并实时监控市场，识别主力拉盘起爆点。

## 核心功能

### 1. 做市商行为指纹生成
- 基于历史数据生成做市商行为特征指纹
- 多维度指标分析（PIR、资金流向、成交量、形态特征等）
- 支持自定义时间范围
- 自动保存指纹数据

### 2. 实时监控与告警
- 实时监听币安永续合约市场
- 基于指纹特征识别主力拉盘起爆点
- 分级告警机制
- 支持钉钉消息推送

### 3. LIGHT 币种深度分析
- 专门针对 LIGHT 币种的做市行为分析
- 支持历史数据回溯
- 详细的交易数据处理

## 目录结构

```
src/research/
├── analyze_light_maker.py   # LIGHT 币种分析工具
├── config.py               # 配置参数
├── data/                   # 数据存储目录
├── fingerprint_manager.py   # 指纹管理器
├── logs/                   # 日志目录
├── mm_binance_realtime.py  # 实时监控工具
└── mm_fingerprint_scanner.py  # 指纹生成工具
```

## 安装与运行

### 环境要求
- Python 3.8+
- asyncio
- pandas
- numpy
- aiohttp
- ccxt
- loguru

### 安装依赖
```bash
pip install -r requirements.txt
```

### 核心配置

在 `config.py` 文件中配置以下参数：

```python
# DingTalk 告警配置
DINGTALK_TOKEN = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
DINGTALK_SECRET = "YOUR_SECRET"

# 实时监控参数
PIR_THRESHOLD = 1.2          # 价格冲击比阈值
VOL_SPIKE_THRESHOLD = 6.0     # 成交量峰值阈值
PUMP_THRESHOLD = 1.2          # 价格涨幅阈值
SHADOW_THRESHOLD = 1.2        # 上影线比例阈值
```

## 使用示例

### 1. 生成做市商行为指纹

```bash
python3 -m src.research.mm_fingerprint_scanner
```

该命令会：
- 分析币安永续合约的历史数据
- 生成多维度的做市商行为指纹
- 将指纹数据保存到 `src/research/data/fingerprints.json`

### 2. 实时监控主力拉盘起爆点

```bash
python3 -m src.research.mm_binance_realtime
```

该命令会：
- 加载已生成的指纹数据
- 实时监听币安永续合约的 1 分钟 K 线数据
- 检测符合指纹特征的主力拉盘起爆点
- 发送告警通知

### 3. 分析 LIGHT 币种做市行为

```bash
python3 -m src.research.analyze_light_maker
```

该命令会：
- 获取 LIGHT 币种的历史交易数据
- 分析其做市商行为特征
- 生成分析报告

## 核心算法

### 1. 价格冲击比 (PIR - Price Impact Ratio)
```python
# PIR = 价格涨幅百分比 / (成交额 / 1,000,000)
pir = price_pct / (est_flow_m / 1e6)
```

### 2. 指纹匹配算法
```python
# 基于多维度指标的加权匹配
match_score = 0
match_score += 30 * (pir >= threshold)        # PIR 匹配 (30分)
match_score += 25 * (vol_spike >= threshold)  # 成交量峰值匹配 (25分)
match_score += 20 * (flow > threshold)       # 资金流向匹配 (20分)
match_score += 15 * (big_order >= threshold)  # 大单占比匹配 (15分)
match_score += 10 * (price_pct > 0.5)        # 价格涨幅匹配 (10分)
```

### 3. 主力拉盘起爆点判定
- 匹配度 >= 70 分
- 结合实时市场数据
- 多维度交叉验证

## 数据说明

### 生成的数据文件

| 文件路径 | 说明 |
|---------|------|
| `src/research/data/fingerprints.json` | 做市商行为指纹数据 |
| `src/research/data/scan_results.csv` | 指纹扫描结果 |
| `src/research/logs/mm_binance_alerts.log` | 告警日志 |

### 数据格式

#### 指纹数据格式
```json
[
  {
    "symbol": "BULLA/USDT:USDT",
    "score": 58.75,
    "metrics": {
      "pir_median": 2.15,
      "window_hit_rate": 0.0,
      "positive_flow_ratio": 0.55,
      "big_order_ratio": 0.3,
      "strong_up_moves": 5,
      "volume_concentration": 0.45,
      "avg_upper_shadow": 0.35,
      "avg_lower_shadow": 0.85,
      "volatility_ratio": 1.2
    },
    "created_at": "2026-01-12T15:38:32.310838",
    "updated_at": "2026-01-12T15:38:32.310838"
  }
]
```

## 告警类型

### 1. 主力拉盘起爆点告警
```
🚀 [🔥 MAIN PUMP ALERT] TRUTHUSDT | Match Score: 85/100 | Price: +1.25% | PIR: 2.35 | Vol Spike: 7.2x | Positive Flow: 80.0% | Big Order: YES | Shadow: 0.15%
```

### 2. 普通做市商活动告警
```
🔥 [MM ALERT] TRUTHUSDT | Score: 45 | Price: +0.80% | PIR: 1.85 | Vol Spike: 5.1x | Shadow: 0.25%
```

## 注意事项

1. **API 限制**：实时监控工具会产生大量 API 请求，请确保您的 API 密钥有足够的请求配额
2. **数据存储**：所有生成的数据会保存在 `src/research/data/` 目录下，请确保有足够的存储空间
3. **告警频率**：根据市场情况，可能会产生大量告警，建议合理调整配置参数
4. **性能优化**：实时监控工具会占用一定的 CPU 和内存资源，请根据服务器配置调整并发数

## 扩展建议

1. **添加更多交易所支持**：当前仅支持币安，可扩展到 OKX、Bybit 等
2. **优化指纹匹配算法**：可考虑使用机器学习模型提高匹配准确率
3. **添加可视化界面**：可开发 Web 界面展示实时监控结果和历史数据
4. **支持自定义策略**：允许用户自定义告警条件和策略

## 许可证

MIT License
