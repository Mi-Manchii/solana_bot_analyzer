# feature_calculator.py
import pandas as pd
from datetime import datetime

def compute_features(address, sigs_with_time):
    if not sigs_with_time:
        return {}

    df = pd.DataFrame(sigs_with_time, columns=['signature', 'block_time'])
    df['datetime'] = pd.to_datetime(df['block_time'], unit='s')
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour

    total_tx = len(df)
    unique_days = df['date'].nunique()
    avg_tx_per_day = total_tx / unique_days if unique_days else 0
    max_tx_day = df.groupby('date').size().max()
    night_tx = df[df['hour'].between(0, 5)].shape[0]
    night_ratio = night_tx / total_tx if total_tx else 0

    df_sorted = df.sort_values('block_time')
    intervals = df_sorted['block_time'].diff().dropna()
    avg_interval = intervals.mean() if not intervals.empty else 0
    median_interval = intervals.median() if not intervals.empty else 0

    feb_start = datetime(2026, 2, 1)
    feb_end = datetime(2026, 2, 24)
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
        'avg_interval_seconds': round(avg_interval, 2),
        'median_interval_seconds': round(median_interval, 2),
        'feb_2026_tx_count': feb_count,
        'feb_2026_active_days': feb_days,
    }
    return features