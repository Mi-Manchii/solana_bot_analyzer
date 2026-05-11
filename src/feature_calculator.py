# src/feature_calculator.py
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from collections import Counter

CORE_DEX_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
    "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "9W959DqEETiGZocYWCQPaJ6LChVY5a4hs7Tpe2T7aB",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
}

PUMP_FUN_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
    "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
}

# [核心修复] Jito MEV 官方小费接收账户大全 (8个节点)
JITO_TIP_ACCOUNTS = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvVkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jMsNCMRXZhzvqtxHQZADWAegZaEUcQMznY9",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7QsBgTijRp1oBRtL2b1pB83P",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdCEjiPuJT1Rnbk"
}

def _entropy(counter):
    total = sum(counter.values())
    if total <= 0:
        return 0
    probs = [count / total for count in counter.values()]
    return -sum(p * np.log2(p) for p in probs if p > 0)

def _coefficient_of_variation(values):
    values = [float(v) for v in values if v is not None]
    if not values:
        return 0
    avg = np.mean(values)
    return float(np.std(values) / avg) if avg > 0 else 0

def compute_features(address, sigs_with_time, transactions=None, err_map=None):
    if not sigs_with_time:
        return {}

    df = pd.DataFrame(sigs_with_time, columns=['signature', 'block_time'])
    df['datetime'] = pd.to_datetime(df['block_time'], unit='s')
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour
    df['weekday'] = df['datetime'].dt.weekday  

    total_tx = len(df)
    unique_days = df['date'].nunique()
    avg_tx_per_day = total_tx / unique_days if unique_days else 0
    max_tx_day = df.groupby('date').size().max()

    df_sorted = df.sort_values('block_time')
    intervals = df_sorted['block_time'].diff().dropna()
    avg_interval = intervals.mean() if not intervals.empty else 0
    median_interval = intervals.median() if not intervals.empty else 0
    std_interval = intervals.std() if not intervals.empty else 0
    cv_interval = std_interval / avg_interval if avg_interval > 0 else 0

    hourly_counts = df['hour'].value_counts().sort_index()
    hourly_probs = hourly_counts / total_tx
    hourly_entropy = -sum(p * np.log2(p) for p in hourly_probs if p > 0)

    # 极小样本熵值平滑惩罚
    if total_tx <= 24:
        hourly_entropy = hourly_entropy * (total_tx / 24.0)

    peak_hour = hourly_counts.idxmax() if not hourly_counts.empty else -1

    daily_counts = df.groupby('date').size()
    daily_std = daily_counts.std() if len(daily_counts) > 1 else 0
    daily_cv = daily_std / avg_tx_per_day if avg_tx_per_day > 0 else 0

    all_dates = pd.Series(sorted(df['date'].unique()))
    if len(all_dates) > 1:
        date_diffs = all_dates.diff().dt.days.dropna()
        max_inactive = date_diffs.max() - 1
    else:
        max_inactive = 0

    failed_count = sum(1 for sig in df['signature'] if err_map and err_map.get(sig, False))
    failed_tx_ratio = failed_count / total_tx if total_tx else 0

    features = {
        'address': address,
        'total_transactions': total_tx,
        'unique_days': unique_days,
        'avg_tx_per_day': round(avg_tx_per_day, 2),
        'max_tx_in_day': max_tx_day,
        'avg_interval_seconds': round(avg_interval, 2),
        'median_interval_seconds': round(median_interval, 2),
        'std_interval_seconds': round(std_interval, 2),
        'cv_interval': round(cv_interval, 4),
        'hourly_entropy': round(hourly_entropy, 4),
        'peak_hour': peak_hour,
        'daily_cv': round(daily_cv, 4),
        'max_inactive_days': max_inactive,
        'failed_tx_ratio': round(failed_tx_ratio, 4),
    }

    # ---------- 微观特征提取 ----------
    if transactions:
        program_counter = Counter()
        instruction_program_counter = Counter()
        instruction_type_counter = Counter()
        instruction_counts = []
        priority_fees = []
        fees = []
        compute_units = []
        
        core_dex_tx = 0
        pump_fun_tx = 0
        jito_tip_tx = 0
        
        tx_detail_count = len(transactions)
        valid_fee_count = 0 
        valid_cu_count = 0

        for tx in transactions:
            tx_programs = set(tx.get('program_ids') or [])
            # [核心修复] 获取提取的全局 Account Keys
            tx_accounts = set(tx.get('account_keys') or [])
            
            instruction_programs = tx.get('instruction_programs') or []
            instruction_types = tx.get('instruction_types') or []
            
            for pid in tx_programs:
                program_counter[pid] += 1
            for pid in instruction_programs:
                instruction_program_counter[pid] += 1
            for ix_type in instruction_types:
                instruction_type_counter[ix_type] += 1
                
            instruction_counts.append(tx.get('instruction_count') or 0)
            
            p_fee = tx.get('priority_fee_lamports')
            if p_fee is not None:
                priority_fees.append(p_fee)
                valid_fee_count += 1
                
            fee = tx.get('fee_lamports')
            if fee is not None:
                fees.append(fee)
                
            cu = tx.get('compute_units_consumed')
            if cu is not None:
                compute_units.append(cu)
                valid_cu_count += 1
            
            if tx_programs & CORE_DEX_PROGRAMS:
                core_dex_tx += 1
            if tx_programs & PUMP_FUN_PROGRAMS:
                pump_fun_tx += 1
            
            # [核心修复] 如果该笔交易交互了任何官方 Jito 小费账户，即判定为 MEV 操作
            if tx_accounts & JITO_TIP_ACCOUNTS:
                jito_tip_tx += 1
                
        unique_programs = len(program_counter)
        program_entropy = _entropy(program_counter)

        token_tx_counter = Counter()
        tx_tokens = []
        for tx in transactions:
            unique_tokens_in_tx = set(tx.get('tokens') or [])
            tx_tokens.append(unique_tokens_in_tx)
            for mint in unique_tokens_in_tx:
                token_tx_counter[mint] += 1
                
        unique_tokens = len(token_tx_counter)
        token_entropy = _entropy(token_tx_counter)

        rare_tokens = {mint for mint, count in token_tx_counter.items() if count <= 2}
        rare_token_txs = sum(1 for tokens in tx_tokens if tokens & rare_tokens)
        unique_instruction_types = len(instruction_type_counter)

        features.update({
            'unique_programs': unique_programs,
            'program_entropy': round(program_entropy, 4),
            'unique_tokens': unique_tokens,
            'token_entropy': round(token_entropy, 4),
            
            'avg_priority_fee_lamports': round(float(np.mean(priority_fees)) if valid_fee_count > 0 else 0, 2),
            'priority_fee_cv': round(_coefficient_of_variation(priority_fees), 4),
            'priority_fee_nonzero_ratio': round(
                sum(1 for f in priority_fees if f > 0) / valid_fee_count if valid_fee_count > 0 else 0, 4
            ),
            'avg_fee_lamports': round(float(np.mean(fees)) if fees else 0, 2),
            'avg_compute_units': round(float(np.mean(compute_units)) if valid_cu_count > 0 else 0, 2),
            
            'avg_instruction_count': round(float(np.mean(instruction_counts)) if instruction_counts else 0, 2),
            'unique_instruction_types': unique_instruction_types,
            'instruction_program_entropy': round(_entropy(instruction_program_counter), 4),
            'instruction_type_entropy': round(_entropy(instruction_type_counter), 4),
            
            'core_dex_interaction_ratio': round(core_dex_tx / tx_detail_count if tx_detail_count else 0, 4),
            'pump_fun_interaction_ratio': round(pump_fun_tx / tx_detail_count if tx_detail_count else 0, 4),
            'new_token_interaction_ratio': round(rare_token_txs / tx_detail_count if tx_detail_count else 0, 4),
            'jito_tip_interaction_ratio': round(jito_tip_tx / tx_detail_count if tx_detail_count else 0, 4),
        })

    return features