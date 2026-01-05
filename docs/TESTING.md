# 测试文档

## 运行测试

### 安装测试依赖

```bash
pip install -r requirements.txt
```

### 运行所有测试

```bash
# 运行所有测试
pytest

# 显示详细输出
pytest -v

# 显示覆盖率
pytest --cov=src tests/
```

### 运行特定测试

```bash
# 运行特定测试文件
pytest tests/test_analyzers.py

# 运行特定测试类
pytest tests/test_analyzers.py::TestTakerFlowAnalyzer

# 运行特定测试方法
pytest tests/test_analyzers.py::TestTakerFlowAnalyzer::test_analyze_with_data
```

### 测试标记

```bash
# 只运行单元测试
pytest -m unit

# 跳过慢速测试
pytest -m "not slow"

# 运行集成测试
pytest -m integration
```

## 测试结构

```
tests/
├── conftest.py              # Pytest 配置和 fixtures
├── test_analyzers.py        # 分析器测试
├── test_dataframe_helpers.py # DataFrame 辅助函数测试
├── test_processor.py        # 数据处理器测试
└── test_connectors.py       # 连接器测试（集成测试）
```

## 测试覆盖率

当前测试覆盖：
- ✅ TakerFlowAnalyzer - 基础功能
- ✅ MultiPlatformAnalyzer - 共识检测
- ✅ WhaleWatcher - 巨鲸检测
- ✅ DataFrame 辅助函数
- ✅ DataProcessor - 数据处理

## 编写新测试

### 示例：测试新的分析器

```python
import pytest
from src.analyzers.your_analyzer import YourAnalyzer

class TestYourAnalyzer:
    """Tests for YourAnalyzer"""
    
    def test_basic_functionality(self):
        """Test basic functionality"""
        analyzer = YourAnalyzer()
        result = analyzer.analyze(sample_data)
        assert result is not None
        assert 'expected_key' in result
```

### 使用 Fixtures

```python
def test_with_fixture(sample_candle_data):
    """Test using fixture"""
    analyzer = TakerFlowAnalyzer()
    result = analyzer.analyze(sample_candle_data)
    assert result['cumulative_net_flow'] > 0
```

## CI/CD 集成

测试可以在 CI/CD 流程中自动运行：

```yaml
# .github/workflows/test.yml (示例)
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest --cov=src tests/
```

## 注意事项

1. **异步测试**: 某些测试需要异步支持，使用 `pytest-asyncio`
2. **网络依赖**: 集成测试可能需要网络连接
3. **测试数据**: 使用 fixtures 提供测试数据，避免硬编码
