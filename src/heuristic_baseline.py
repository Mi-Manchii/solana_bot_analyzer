import numpy as np
import pandas as pd
import json

BOT_TYPE_MAP = {
    0: "正常用户 (Human)",
    11: "MEV - 跨池套利",             
    12: "MEV - 清算者",             
    13: "MEV - 三明治/抢跑", 
    14: "MEV - 流动性狙击",             
    20: "CEX - 热钱包/归集",    
    30: "DEX - 自动化做市",        
    61: "通用 - 垃圾交易 (Spam)",             
    90: "未归类自动化"               
}

def determine_bot_type_id(row):
    """基于开题报告中 Solana 特有特征的机器人行为分型逻辑 [cite: 147, 154, 166]"""
    if row.get("heuristic_is_bot", 0) == 0: return 0 
    
    avg_tx = row.get("avg_tx_per_day", 0)
    jito_ratio = row.get("jito_tip_interaction_ratio", 0)
    pump_ratio = row.get("pump_fun_interaction_ratio", 0)
    p_fee_cv = row.get("priority_fee_cv", 0)
    p_fee_ratio = row.get("priority_fee_nonzero_ratio", 0)
    avg_cu = row.get("avg_compute_units", 0)
    ix_types = row.get("unique_instruction_types", 0)
    failed_ratio = row.get("failed_tx_ratio", 0)

    # 1. MEV - 三明治攻击/高级抢跑 (Jito 核心用户) [cite: 172]
    if jito_ratio > 0.02: return 13
        
    # 2. MEV - 流动性狙击 (Pump.fun 打新，高动态费率特征) [cite: 139]
    if pump_ratio >= 0.4 and p_fee_ratio > 0.5 and p_fee_cv > 1.2: return 14

    # 3. 通用 - 垃圾交易 (Spam，指令极单一或失败率极高)
    if avg_tx >= 1200 and (ix_types <= 1 or failed_ratio >= 0.5): return 61

    # 4. MEV - 跨池套利 (高核心 DEX 交互 + 多指令复杂度) [cite: 171]
    if row.get("core_dex_interaction_ratio", 0) >= 0.5 and avg_cu > 50000: return 11
        
    # 5. MEV - 清算者 (极高 CU 消耗) [cite: 40]
    if avg_cu >= 300000: return 12

    # 6. DEX - 自动化做市 (稳定低延迟交互) [cite: 173]
    if avg_tx >= 500 and failed_ratio <= 0.05: return 30

    return 90

def score_addresses(df):
    scored = df.copy()
    score = np.zeros(len(scored), dtype=float)

    rules = {
        "rule_extreme_frequency": scored.get("avg_tx_per_day", 0) >= 200, 
        "rule_no_sleep": (scored.get("max_inactive_days", 1) <= 0) & (scored.get("unique_days", 0) > 1),
        "rule_24h_active": (scored.get("hourly_entropy", 0) >= 3.8) & (scored.get("unique_days", 0) > 1),  
        "rule_fixed_pattern": scored.get("cv_interval", 1) <= 0.8, 
        "rule_high_fee_willingness": scored.get("priority_fee_nonzero_ratio", 0) >= 0.4,
        "rule_scripted_fee": (scored.get("priority_fee_nonzero_ratio", 0) >= 0.3) & (scored.get("priority_fee_cv", 1) <= 0.1),
    }

    weights = {
        "rule_extreme_frequency": 1.0, "rule_no_sleep": 2.5, "rule_24h_active": 2.0,        
        "rule_fixed_pattern": 1.5, "rule_high_fee_willingness": 1.0, "rule_scripted_fee": 2.5,  
    }

    for name, mask in rules.items():
        scored[name] = mask.astype(int)
        score += scored[name].to_numpy() * weights[name]

    scored["heuristic_score"] = score
    # 一票否决与得分判定
    override = (scored.get("avg_tx_per_day", 0) >= 300) | ((scored.get("hourly_entropy", 0) >= 4.2) & (scored.get("unique_days", 0) > 1))
    scored["heuristic_is_bot"] = ((score >= 6.0) | override).astype(int)
    scored["bot_type_id"] = scored.apply(determine_bot_type_id, axis=1)
    scored["bot_type_name"] = scored["bot_type_id"].map(BOT_TYPE_MAP)
    return scored