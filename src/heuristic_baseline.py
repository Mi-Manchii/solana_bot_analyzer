# src/heuristic_baseline.py
import numpy as np
import pandas as pd
import json

from .paper_utils import ensure_output_dir, load_features, save_dataframe

BOT_TYPE_MAP = {
    0: "正常用户 (Human)",
    11: "MEV - 跨池套利 (MEV - Arbitrage)",             
    12: "MEV - 清算者 (MEV - Liquidation)",             
    13: "MEV - 三明治/抢跑 (MEV - Sandwich/Front-run)", 
    14: "MEV - 流动性狙击 (MEV - Sniping)",             
    20: "CEX - 热钱包/归集 (CEX - Wallets/Funding)",    
    30: "DEX - 自动化做市 (DEX - Market Maker)",        
    60: "通用 - 空投女巫 (General - Sybil Farmer)",     
    61: "通用 - 垃圾交易 (General - Spam)",             
    90: "未归类自动化 (Non-attributable)"               
}

def _series(df, col, default=0):
    if col not in df.columns:
        return pd.Series(default, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)

def determine_bot_type_id(row):
    """基于最新资金开销特征 (Fee CV) 的高级推断逻辑"""
    if row["heuristic_is_bot"] == 0:
        return 0 
    
    avg_tx = row.get("avg_tx_per_day", 0)
    unique_tokens = row.get("unique_tokens", 0)
    
    pump_fun_ratio = row.get("pump_fun_interaction_ratio", 0)
    core_dex_ratio = row.get("core_dex_interaction_ratio", 0)
    
    priority_fee_ratio = row.get("priority_fee_nonzero_ratio", 0)
    priority_fee_cv = row.get("priority_fee_cv", 0)
    avg_priority_fee = row.get("avg_priority_fee_lamports", 0)
    
    jito_tip_ratio = row.get("jito_tip_interaction_ratio", 0)
    avg_cu = row.get("avg_compute_units", 0) 
    failed_tx_ratio = row.get("failed_tx_ratio", 0) 

    # 1. MEV - 三明治攻击/高级抢跑 (Jito 核心用户)
    if jito_tip_ratio > 0.05:
        return 13
        
    # 2. MEV - 流动性狙击 (Pump.fun 打新机器，特征：高动态费率)
    if pump_fun_ratio >= 0.5 and priority_fee_ratio > 0.5 and priority_fee_cv > 1.5:
        return 14

    # 3. 通用 - 垃圾交易 (Spam，特征：硬编码低费率 或 极高失败率)
    if avg_tx >= 1000 and (failed_tx_ratio >= 0.4 or (priority_fee_cv < 0.1 and avg_priority_fee < 5000)):
        return 61

    # 4. MEV - 跨池套利 (特征：交互海量代币，消耗极高计算单元)
    if core_dex_ratio >= 0.5 and unique_tokens > 50 and avg_cu > 50000:
        return 11
        
    # 5. MEV - 清算者 (极高 CU，单一代币)
    if avg_cu >= 400000 and core_dex_ratio >= 0.2:
        return 12

    # 6. DEX - 自动化做市 (稳定交互)
    if avg_tx >= 500 and failed_tx_ratio <= 0.1 and core_dex_ratio >= 0.5:
        return 30

    # 7. 兜底
    return 90

def score_addresses(df):
    scored = df.copy()
    score = np.zeros(len(scored), dtype=float)

    rules = {
        "rule_extreme_frequency": _series(scored, "avg_tx_per_day") >= 200, 
        "rule_large_tx_volume": _series(scored, "total_transactions") >= 1500, 
        "rule_no_sleep": (_series(scored, "max_inactive_days") <= 0) & (_series(scored, "unique_days") > 1),
        "rule_24h_active": (_series(scored, "hourly_entropy") >= 3.8) & (_series(scored, "unique_days") > 1),  
        "rule_machine_speed": (_series(scored, "avg_interval_seconds", default=10**9) > 0) & (_series(scored, "avg_interval_seconds", default=10**9) <= 20),
        "rule_fixed_pattern": _series(scored, "cv_interval") <= 0.8, 
        "rule_many_tokens": _series(scored, "unique_tokens") >= 100,
        "rule_high_fee_willingness": _series(scored, "priority_fee_nonzero_ratio") >= 0.4,
        "rule_dex_centric": _series(scored, "core_dex_interaction_ratio") >= 0.5,
        
        # 硬编码脚本费率检测
        "rule_scripted_fee": (_series(scored, "priority_fee_nonzero_ratio") >= 0.3) & (_series(scored, "priority_fee_cv") <= 0.1),
    }

    weights = {
        "rule_extreme_frequency": 1.0, "rule_large_tx_volume": 1.0,
        "rule_no_sleep": 2.5, "rule_24h_active": 2.0,        
        "rule_machine_speed": 1.5, "rule_fixed_pattern": 1.5,     
        "rule_many_tokens": 1.0, "rule_high_fee_willingness": 1.0, 
        "rule_dex_centric": 1.0, "rule_scripted_fee": 2.5,  
    }

    for name, mask in rules.items():
        scored[name] = mask.astype(int)
        score += scored[name].to_numpy() * weights[name]

    scored["heuristic_score"] = score
    base_is_bot = (score >= 6.0).astype(int) 
    
    # 绝对一票否决
    override_bio_limit = (_series(scored, "avg_tx_per_day") >= 300).astype(int)
    override_perfect_entropy = ((_series(scored, "hourly_entropy") >= 4.2) & (_series(scored, "unique_days") > 1)).astype(int)
    override_hardcoded_script = ((_series(scored, "priority_fee_nonzero_ratio") >= 0.8) & (_series(scored, "priority_fee_cv") <= 0.05)).astype(int)
    
    scored["heuristic_is_bot"] = base_is_bot | override_bio_limit | override_perfect_entropy | override_hardcoded_script
    
    scored["bot_type_id"] = scored.apply(determine_bot_type_id, axis=1)
    scored["bot_type_name"] = scored["bot_type_id"].map(BOT_TYPE_MAP)
    
    return scored

def run_heuristic_baseline(output_dir=None, feature_file="features.csv"):
    output_dir = ensure_output_dir(output_dir)
    df = load_features(output_dir, feature_file)
    scored = score_addresses(df)
    
    # 统一输出名称，方便下游读取
    out_path = save_dataframe(scored, output_dir / "heuristic_scores_final.csv")
    
    with open(output_dir / "bot_label_mapping.json", "w", encoding="utf-8") as f:
        json.dump(BOT_TYPE_MAP, f, ensure_ascii=False, indent=4)

    print(f"✅ 启发式标注完成! 已生成包含最新 Priority Fee 策略分类的数据: {out_path}")
    return scored

if __name__ == "__main__":
    run_heuristic_baseline()