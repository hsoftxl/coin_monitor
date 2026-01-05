# 通知通道配置说明

## 概述

系统支持**双通道通知**：
- **主通道**：用于常规信号通知（A+/A级信号、市场共识等）
- **专用通道**：专门用于**拉盘**和**稳步上涨**信号通知

## 配置方式

### 方式一：使用环境变量（推荐）

在 `.env` 文件中配置：

```bash
# ==================== 主通道配置 ====================
ENABLE_DINGTALK=true
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_MAIN_TOKEN
DINGTALK_SECRET=YOUR_MAIN_SECRET

ENABLE_WECHAT=false
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_MAIN_KEY

# ==================== 拉盘/稳步上涨专用通道 ====================
# 启用专用通道（设置为 true 后，拉盘和稳步上涨信号会发送到此通道）
ENABLE_PUMP_GROWTH_CHANNEL=true

# 钉钉专用通道
PUMP_GROWTH_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_PUMP_GROWTH_TOKEN
PUMP_GROWTH_DINGTALK_SECRET=YOUR_PUMP_GROWTH_SECRET

# 企业微信专用通道
PUMP_GROWTH_WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_PUMP_GROWTH_KEY
```

### 方式二：直接修改配置文件

编辑 `src/config.py`：

```python
# 拉盘/稳步上涨专用通道
ENABLE_PUMP_GROWTH_CHANNEL = True
PUMP_GROWTH_DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
PUMP_GROWTH_DINGTALK_SECRET = "YOUR_SECRET"
PUMP_GROWTH_WECHAT_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
```

## 信号路由规则

### 发送到专用通道的信号

以下信号会优先发送到专用通道（如果已配置）：

1. **🚀 主力拉盘启动警报** (`send_early_pump_alert`)
   - 1分钟主力拉盘检测
   - A+级信号

2. **💎 稳步上涨趋势确认** (`send_steady_growth_alert`)
   - 15分钟稳步上涨趋势
   - A级信号

3. **⚡ 实时拉盘警报** (`send_realtime_pump_alert`)
   - WebSocket实时监控捕获的拉盘信号

### 发送到主通道的信号

以下信号发送到主通道：

- 市场共识通知
- 其他A+/A级信号（非拉盘/稳步上涨）
- B级信号汇总
- 巨鲸监控通知

## 回退机制

如果配置了 `ENABLE_PUMP_GROWTH_CHANNEL=true` 但未配置专用通道的 webhook，系统会：
- **自动回退到主通道**发送拉盘/稳步上涨信号
- 确保重要信号不会丢失

## 使用场景

### 场景1：分离重要信号

- **主通道**：接收所有常规信号，用于日常监控
- **专用通道**：只接收拉盘和稳步上涨信号，用于快速响应

### 场景2：多团队协作

- **主通道**：发送给分析团队
- **专用通道**：发送给交易团队，专注于拉盘和稳步上涨机会

### 场景3：单通道模式

如果 `ENABLE_PUMP_GROWTH_CHANNEL=false` 或未配置专用通道：
- 所有信号（包括拉盘/稳步上涨）都发送到主通道
- 保持原有行为

## 配置示例

### 示例1：启用专用通道（钉钉）

```bash
# 主通道
ENABLE_DINGTALK=true
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=MAIN_TOKEN
DINGTALK_SECRET=MAIN_SECRET

# 专用通道
ENABLE_PUMP_GROWTH_CHANNEL=true
PUMP_GROWTH_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=PUMP_TOKEN
PUMP_GROWTH_DINGTALK_SECRET=PUMP_SECRET
```

### 示例2：仅使用主通道

```bash
# 主通道
ENABLE_DINGTALK=true
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=MAIN_TOKEN
DINGTALK_SECRET=MAIN_SECRET

# 不启用专用通道（或设置为false）
ENABLE_PUMP_GROWTH_CHANNEL=false
```

## 注意事项

1. **优先级**：如果启用了专用通道且配置了webhook，拉盘/稳步上涨信号**只**发送到专用通道，不会同时发送到主通道
2. **兼容性**：如果不配置专用通道，系统行为与之前完全一致
3. **安全性**：建议使用环境变量配置，避免将敏感信息提交到代码仓库

## 验证配置

运行程序后，查看日志：

```
✅ 通知服务已启用
  - 钉钉推送: 已启用
  - 专用通道: 已启用（拉盘/稳步上涨）
```

当触发拉盘或稳步上涨信号时，日志会显示：

```
🚀 触发主力拉盘警报 [BTC/USDT]，立即推送！
💎 触发稳步上涨警报 [ETH/USDT]，推送通知...
```
