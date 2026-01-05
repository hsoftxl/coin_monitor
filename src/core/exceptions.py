"""
自定义异常类
提供更精确的异常类型，替代通用的 Exception
"""


class CoinMonitorError(Exception):
    """基础异常类"""
    pass


class ExchangeConnectionError(CoinMonitorError):
    """交易所连接错误"""
    pass


class DataFetchError(CoinMonitorError):
    """数据获取错误"""
    pass


class AnalysisError(CoinMonitorError):
    """分析错误"""
    pass


class ConfigurationError(CoinMonitorError):
    """配置错误"""
    pass


class NotificationError(CoinMonitorError):
    """通知错误"""
    pass
