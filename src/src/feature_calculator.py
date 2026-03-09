# src/feature_calculator.py
import pandas as pd
import numpy as np
from datetime import datetime
from collections import Counter

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
    daily_std = daily_counts.std()
    daily_cv = daily_std / avg_tx_per_day if avg_tx_per_day > 0 else 0

    # 最长连续无交易天数
    all_dates = pd.Series(sorted(df['date'].unique()))
    if len(all_dates) > 1:
        date_diffs = all_dates.diff().dt.days.dropna()
        max_inactive = date_diffs.max() - 1
    else:
        max_inactive = 0

    # 近期交易比例（最近7天）
    now = datetime.utcnow()
    recent_7d_start = now - pd.Timedelta(days=7)
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
        # 程序ID统计
        program_counter = Counter()
        for tx in transactions:
            for pid in tx.get('program_ids', []):
                program_counter[pid] += 1
        unique_programs = len(program_counter)
        total_program_calls = sum(program_counter.values())
        if total_program_calls > 0:
            probs = [c/total_program_calls for c in program_counter.values()]
            program_entropy = -sum(p * np.log2(p) for p in probs)
        else:
            program_entropy = 0

        # 代币Mint统计（统计出现过的交易次数）
        token_tx_counter = Counter()
        for tx in transactions:
            # 去重：同一交易中同一代币只计一次
            unique_tokens_in_tx = set(tx.get('tokens', []))
            for mint in unique_tokens_in_tx:
                token_tx_counter[mint] += 1
        unique_tokens = len(token_tx_counter)
        total_token_txs = sum(token_tx_counter.values())
        if total_token_txs > 0:
            probs = [c/total_token_txs for c in token_tx_counter.values()]
            token_entropy = -sum(p * np.log2(p) for p in probs)
        else:
            token_entropy = 0

        features.update({
            'unique_programs': unique_programs,
            'program_entropy': round(program_entropy, 4),
            'unique_tokens': unique_tokens,
            'token_entropy': round(token_entropy, 4)
        })

    return features