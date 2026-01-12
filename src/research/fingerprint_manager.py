import json
import os
from datetime import datetime
from loguru import logger

class FingerprintManager:
    """
    指纹管理器，用于存储和管理做市商行为特征指纹
    """
    def __init__(self):
        # 将指纹文件放在同级的 data 目录
        self.fingerprints_file = os.path.join(os.path.dirname(__file__), "data", "fingerprints.json")
        self.fingerprints = self.load_fingerprints()
        self.thresholds = {
            "min_score": 50,  # 最低评分阈值
            "min_pir": 1.2,   # 最低PIR阈值
            "min_vol_spike": 4.0,  # 最低成交量峰值阈值
            "min_positive_flow": 0.5,  # 最低正资金流入占比
            "min_big_order_ratio": 0.2  # 最低大单占比
        }
        
    def load_fingerprints(self):
        """
        从文件加载指纹数据
        """
        try:
            if os.path.exists(self.fingerprints_file):
                with open(self.fingerprints_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"✅ Loaded {len(data)} fingerprints from {self.fingerprints_file}")
                    return data
            else:
                logger.info(f"📁 Fingerprint file not found, creating new one")
                return []
        except Exception as e:
            logger.error(f"❌ Failed to load fingerprints: {e}")
            return []
    
    def save_fingerprints(self):
        """
        保存指纹数据到文件
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.fingerprints_file), exist_ok=True)
            with open(self.fingerprints_file, 'w', encoding='utf-8') as f:
                json.dump(self.fingerprints, f, indent=2, ensure_ascii=False)
            logger.success(f"✅ Saved {len(self.fingerprints)} fingerprints to {self.fingerprints_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save fingerprints: {e}")
    
    def add_fingerprint(self, symbol, metrics, score):
        """
        添加新指纹
        """
        fingerprint = {
            "symbol": symbol,
            "score": score,
            "metrics": metrics,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 检查是否已存在
        existing_index = next((i for i, f in enumerate(self.fingerprints) if f["symbol"] == symbol), None)
        if existing_index is not None:
            # 更新现有指纹
            self.fingerprints[existing_index] = fingerprint
            logger.info(f"🔄 Updated fingerprint for {symbol}")
        else:
            # 添加新指纹
            self.fingerprints.append(fingerprint)
            logger.info(f"➕ Added new fingerprint for {symbol}")
        
        # 按评分排序
        self.fingerprints.sort(key=lambda x: x["score"], reverse=True)
        # 只保留前100个指纹
        self.fingerprints = self.fingerprints[:100]
        # 保存
        self.save_fingerprints()
    
    def get_top_fingerprints(self, limit=20):
        """
        获取评分最高的指纹
        """
        return [f for f in self.fingerprints if f["score"] >= self.thresholds["min_score"]][:limit]
    
    def get_fingerprint(self, symbol):
        """
        获取特定币种的指纹
        """
        return next((f for f in self.fingerprints if f["symbol"] == symbol), None)
    
    def is_valid_fingerprint(self, symbol, real_time_metrics):
        """
        验证实时指标是否符合指纹特征
        """
        fingerprint = self.get_fingerprint(symbol)
        if not fingerprint:
            return False, 0
        
        # 计算匹配得分
        match_score = 0
        max_score = 100
        
        # 1. PIR 匹配 (30分)
        if real_time_metrics.get("pir") >= fingerprint["metrics"].get("pir_median", self.thresholds["min_pir"]):
            match_score += 30
        
        # 2. 成交量峰值匹配 (25分)
        if real_time_metrics.get("vol_spike") >= fingerprint["metrics"].get("vol_spike", self.thresholds["min_vol_spike"]):
            match_score += 25
        
        # 3. 资金流向匹配 (20分)
        if real_time_metrics.get("positive_flow_ratio", 0) >= fingerprint["metrics"].get("positive_flow_ratio", self.thresholds["min_positive_flow"]):
            match_score += 20
        
        # 4. 大单占比匹配 (15分)
        if real_time_metrics.get("big_order_ratio", 0) >= fingerprint["metrics"].get("big_order_ratio", self.thresholds["min_big_order_ratio"]):
            match_score += 15
        
        # 5. 价格涨幅匹配 (10分)
        if real_time_metrics.get("price_pct") > 0.5:
            match_score += 10
        
        # 匹配度 >= 70 分视为有效匹配
        return match_score >= 70, match_score
    
    def update_thresholds(self, new_thresholds):
        """
        更新阈值配置
        """
        self.thresholds.update(new_thresholds)
        logger.info(f"🔧 Updated thresholds: {self.thresholds}")
    
    def clear_fingerprints(self):
        """
        清空所有指纹
        """
        self.fingerprints = []
        self.save_fingerprints()
        logger.info("🗑️  Cleared all fingerprints")
    
    def get_fingerprint_stats(self):
        """
        获取指纹统计信息
        """
        if not self.fingerprints:
            return {"total": 0, "avg_score": 0, "active": 0}
        
        avg_score = sum(f["score"] for f in self.fingerprints) / len(self.fingerprints)
        active_count = len([f for f in self.fingerprints if f["score"] >= self.thresholds["min_score"]])
        
        return {
            "total": len(self.fingerprints),
            "avg_score": round(avg_score, 2),
            "active": active_count,
            "thresholds": self.thresholds
        }
