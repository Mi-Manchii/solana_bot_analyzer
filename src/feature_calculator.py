import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import Counter

# 核心协议与小费账户定义
CORE_DEX_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
}

JITO_TIP_ACCOUNTS = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jMsNCMRXZhzvqtxHQZADWAegZaEUcQMznY9",
}

def _entropy(counter):
    total = sum(counter.values())
    if total <= 0: return 0
    probs = [count / total for count in counter.values()]
    return -sum(p * np.log2(p) for p in probs if p > 0)

def _coefficient_of_variation(values):
    values = [float(v) for v in values if v is not None]
    if not values: return 0
    avg = np.mean(values)
    return float(np.std(values) / avg) if avg > 0 else 0

def compute_features(address, sigs_with_time, transactions=None, err_map=None):
    if not sigs_with_time: return {}

    df = pd.DataFrame(sigs_with_time, columns=['signature', 'block_time'])
    df['datetime'] = pd.to_datetime(df['block_time'], unit='s')
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour

    total_tx = len(df)
    unique_days = df['date'].nunique()
    avg_tx_per_day = total_tx / unique_days if unique_days else 0

    # 修复：鲁棒的时间间隔统计
    df_sorted = df.sort_values('block_time')
    intervals = df_sorted['block_time'].diff().dropna()
    if not intervals.empty:
        # 剔除 99 分位数以上的离群值，修复 features.csv 中的 CV 爆表问题
        upper_limit = np.percentile(intervals, 99)
        filtered = intervals[intervals <= upper_limit]
        cv_interval = filtered.std() / filtered.mean() if filtered.mean() > 0 else 0
    else:
        cv_interval = 0

    # 基础特征构建
    features = {
        'address': address,
        'total_transactions': total_tx,
        'unique_days': unique_days,
        'avg_tx_per_day': round(avg_tx_per_day, 2),
        'cv_interval': round(cv_interval, 4),
        'failed_tx_ratio': round(sum(1 for s in df['signature'] if err_map and err_map.get(s, False)) / total_tx, 4)
    }

    # 详情特征提取
    if transactions:
        program_counter = Counter()
        instruction_type_counter = Counter()
        compute_units = []
        jito_tip_tx = 0
        tx_detail_count = len(transactions)

        for tx in transactions:
            tx_programs = set(tx.get('program_ids') or [])
            tx_accounts = set(tx.get('account_keys') or [])
            for pid in tx_programs: program_counter[pid] += 1
            for ix in (tx.get('instruction_types') or []): instruction_type_counter[ix] += 1
            if tx.get('compute_units_consumed') is not None: compute_units.append(tx['compute_units_consumed'])
            if tx_accounts & JITO_TIP_ACCOUNTS: jito_tip_tx += 1

        features.update({
            'unique_instruction_types': len(instruction_type_counter),
            'avg_compute_units': round(float(np.mean(compute_units)) if compute_units else 0, 2),
            'jito_tip_interaction_ratio': round(jito_tip_tx / tx_detail_count, 4),
        })
    return features