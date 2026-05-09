# src/feature_calculator.py
import pandas as pd
import numpy as np
# [Bug Fix] 引入 timezone 解决时间弃用警告
from datetime import datetime, timezone
from collections import Counter


CORE_DEX_PROGRAMS = {
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",
    # Raydium
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
    "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS",
    # Orca
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "9W959DqEETiGZocYWCQPaJ6LChVY5a4hs7Tpe2T7aB",
    # PumpSwap
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
}

PUMP_FUN_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
    "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
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


def compute_features(address, sigs_with_time, transactions=None):
    """
    计算地址的特征。
    如果提供了 transactions 列表（每个元素包含 program_ids 和 tokens），
    则额外计算程序多样性和代币多样性特征。
    """
    if not sigs_with_time:
        return {}

    df = pd.DataFrame(sigs_with_time, columns=['signature', 'block_time'])
    df['datetime'] = pd.to_datetime(df['block_time'], unit='s')
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour
    df['weekday'] = df['datetime'].dt.weekday  # 0=Monday, 6=Sunday

    total_tx = len(df)
    unique_days = df['date'].nunique()
    avg_tx_per_day = total_tx / unique_days if unique_days else 0
    max_tx_day = df.groupby('date').size().max()

    # 夜间交易比例 (0-5点)
    night_tx = df[df['hour'].between(0, 5)].shape[0]
    night_ratio = night_tx / total_tx if total_tx else 0

    # 周末交易比例 (周六=5, 周日=6)
    weekend_tx = df[df['weekday'].isin([5, 6])].shape[0]
    weekend_ratio = weekend_tx / total_tx if total_tx else 0

    # 交易间隔特征
    df_sorted = df.sort_values('block_time')
    intervals = df_sorted['block_time'].diff().dropna()
    avg_interval = intervals.mean() if not intervals.empty else 0
    median_interval = intervals.median() if not intervals.empty else 0
    std_interval = intervals.std() if not intervals.empty else 0
    cv_interval = std_interval / avg_interval if avg_interval > 0 else 0

    # 日内交易分布熵（基于小时）
    hourly_counts = df['hour'].value_counts().sort_index()
    hourly_probs = hourly_counts / total_tx
    hourly_entropy = -sum(p * np.log2(p) for p in hourly_probs if p > 0)

    peak_hour = hourly_counts.idxmax() if not hourly_counts.empty else -1

    # 每日交易数的变异系数
    daily_counts = df.groupby('date').size()
    daily_std = daily_counts.std() if len(daily_counts) > 1 else 0
    daily_cv = daily_std / avg_tx_per_day if avg_tx_per_day > 0 else 0

    # 最长连续无交易天数
    all_dates = pd.Series(sorted(df['date'].unique()))
    if len(all_dates) > 1:
        date_diffs = all_dates.diff().dt.days.dropna()
        max_inactive = date_diffs.max() - 1
    else:
        max_inactive = 0

    # 近期交易比例（最近7天）
    # [Bug Fix] 使用带时区的 datetime 解决弃用警告
    now = datetime.now(timezone.utc)
    # 将 now 转为无时区时间以便于和 df['datetime'] 比较（因为 pd.to_datetime 默认是无时区的）
    now_naive = now.replace(tzinfo=None)
    recent_7d_start = now_naive - pd.Timedelta(days=7)
    recent_tx = df[df['datetime'] >= recent_7d_start].shape[0]
    recent_ratio_7d = recent_tx / total_tx if total_tx else 0

    # 2026年2月相关特征
    feb_start = datetime(2026, 2, 1)
    feb_end = datetime(2026, 2, 28)
    feb_txs = df[(df['datetime'] >= feb_start) & (df['datetime'] <= feb_end)]
    feb_count = len(feb_txs)
    feb_days = feb_txs['date'].nunique() if not feb_txs.empty else 0

    features = {
        'address': address,
        'total_transactions': total_tx,
        'unique_days': unique_days,
        'avg_tx_per_day': round(avg_tx_per_day, 2),
        'max_tx_in_day': max_tx_day,
        'night_ratio': round(night_ratio, 4),
        'weekend_ratio': round(weekend_ratio, 4),
        'avg_interval_seconds': round(avg_interval, 2),
        'median_interval_seconds': round(median_interval, 2),
        'std_interval_seconds': round(std_interval, 2),
        'cv_interval': round(cv_interval, 4),
        'hourly_entropy': round(hourly_entropy, 4),
        'peak_hour': peak_hour,
        'daily_cv': round(daily_cv, 4),
        'max_inactive_days': max_inactive,
        'recent_tx_ratio_7d': round(recent_ratio_7d, 4),
        'feb_2026_tx_count': feb_count,
        'feb_2026_active_days': feb_days,
    }

    # 如果提供了交易详情，计算程序/代币多样性
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
        for tx in transactions:
            tx_programs = set(tx.get('program_ids', []))
            for pid in tx_programs:
                program_counter[pid] += 1
            for pid in tx.get('instruction_programs', []):
                instruction_program_counter[pid] += 1
            for ix_type in tx.get('instruction_types', []):
                instruction_type_counter[ix_type] += 1
            instruction_counts.append(tx.get('instruction_count', 0) or 0)
            priority_fees.append(tx.get('priority_fee_lamports', 0) or 0)
            fees.append(tx.get('fee_lamports', 0) or 0)
            compute_units.append(tx.get('compute_units_consumed', 0) or 0)
            if tx_programs & CORE_DEX_PROGRAMS:
                core_dex_tx += 1
            if tx_programs & PUMP_FUN_PROGRAMS:
                pump_fun_tx += 1
                
        unique_programs = len(program_counter)
        total_program_calls = sum(program_counter.values())
        program_entropy = _entropy(program_counter)

        token_tx_counter = Counter()
        tx_tokens = []
        for tx in transactions:
            unique_tokens_in_tx = set(tx.get('tokens', []))
            tx_tokens.append(unique_tokens_in_tx)
            for mint in unique_tokens_in_tx:
                token_tx_counter[mint] += 1
        unique_tokens = len(token_tx_counter)
        total_token_txs = sum(token_tx_counter.values())
        token_entropy = _entropy(token_tx_counter)

        # 没有代币创建时间时，用“低复用代币交易占比”近似新代币/短生命周期代币参与度。
        rare_tokens = {mint for mint, count in token_tx_counter.items() if count <= 2}
        rare_token_txs = sum(1 for tokens in tx_tokens if tokens & rare_tokens)
        tx_detail_count = len(transactions)
        
        # [开题报告对齐] 新增指令类型多样性特征
        unique_instruction_types = len(instruction_type_counter)

        features.update({
            'unique_programs': unique_programs,
            'program_entropy': round(program_entropy, 4),
            'unique_tokens': unique_tokens,
            'token_entropy': round(token_entropy, 4),
            'avg_priority_fee_lamports': round(float(np.mean(priority_fees)) if priority_fees else 0, 2),
            'priority_fee_cv': round(_coefficient_of_variation(priority_fees), 4),
            'priority_fee_nonzero_ratio': round(
                sum(1 for fee in priority_fees if fee > 0) / tx_detail_count if tx_detail_count else 0,
                4
            ),
            'avg_fee_lamports': round(float(np.mean(fees)) if fees else 0, 2),
            'avg_compute_units': round(float(np.mean(compute_units)) if compute_units else 0, 2),
            'avg_instruction_count': round(float(np.mean(instruction_counts)) if instruction_counts else 0, 2),
            'unique_instruction_types': unique_instruction_types,  # 新增
            'instruction_program_entropy': round(_entropy(instruction_program_counter), 4),
            'instruction_type_entropy': round(_entropy(instruction_type_counter), 4),
            'core_dex_interaction_ratio': round(core_dex_tx / tx_detail_count if tx_detail_count else 0, 4),
            'pump_fun_interaction_ratio': round(pump_fun_tx / tx_detail_count if tx_detail_count else 0, 4),
            'new_token_interaction_ratio': round(
                rare_token_txs / tx_detail_count if tx_detail_count else 0,
                4
            ),
        })

    return features