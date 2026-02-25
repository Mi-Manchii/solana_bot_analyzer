# main.py
import sys
from pathlib import Path

# 将 src 目录添加到 Python 路径
sys.path.append(str(Path(__file__).parent / "src"))

import time
import pandas as pd
from datetime import datetime

# 从 src 导入各个模块
from src.config import (
    SOURCE_NAME, SOURCE_URL,
    MIN_CONTINUOUS_DAYS, MIN_TX_IN_WINDOW, FETCH_LIMIT
)
from src.address_fetcher import fetch_address_list
from src.transaction_fetcher import TransactionFetcher
from src.validator import find_best_continuous_window
from src.feature_calculator import compute_features
from src.utils import timestamp_to_date

def main():
    candidates = fetch_address_list()
    if not candidates:
        print("无法获取地址列表，退出。")
        return

    fetcher = TransactionFetcher()
    selected_address = None
    selected_sigs = None
    window_info = None

    print("开始逐个测试地址...")
    for addr in candidates:
        print(f"\n测试地址: {addr}")
        sigs = fetcher.get_signatures_with_time(addr, limit=FETCH_LIMIT)
        print(f"获取到 {len(sigs)} 条签名")

        if len(sigs) < MIN_TX_IN_WINDOW:
            print(f"  签名总数不足{MIN_TX_IN_WINDOW}，跳过")
            continue

        found, start, end, tx_count, max_days = find_best_continuous_window(sigs)
        if found and tx_count >= MIN_TX_IN_WINDOW:
            print(f"  ✅ 符合条件！连续{max_days}天，其中7天窗口交易数={tx_count}")
            selected_address = addr
            selected_sigs = sigs
            window_info = (start, end, tx_count, max_days)
            break
        else:
            print(f"  不符合条件（最长连续{max_days}天，7天窗口交易数={tx_count if found else '无窗口'}）")
        time.sleep(1)

    if not selected_address:
        print("未找到符合条件的地址，请尝试更多来源或调整条件。")
        return

    all_times = [ts for _, ts in selected_sigs]
    first_seen = datetime.utcfromtimestamp(min(all_times)).strftime('%Y-%m-%d')
    last_seen = datetime.utcfromtimestamp(max(all_times)).strftime('%Y-%m-%d')
    start_str = window_info[0].strftime('%Y-%m-%d')
    end_str = window_info[1].strftime('%Y-%m-%d')

    addr_row = {
        'address': selected_address,
        'source_label': SOURCE_NAME,
        'source_link': SOURCE_URL,
        'first_seen': first_seen,
        'last_seen': last_seen,
        'active_days': window_info[3],
        'tx_count_7d': window_info[2],
        'window_start': start_str,
        'window_end': end_str,
        'total_tx_available': len(selected_sigs)
    }
    pd.DataFrame([addr_row]).to_csv('addresses.csv', index=False)
    print("\n✅ addresses.csv 已生成")

    features = compute_features(selected_address, selected_sigs)
    pd.DataFrame([features]).to_csv('features.csv', index=False)
    print("✅ features.csv 已生成")

    print("\naddresses.csv 内容:")
    print(pd.read_csv('addresses.csv').to_string())
    print("\nfeatures.csv 内容:")
    print(pd.read_csv('features.csv').to_string())

if __name__ == "__main__":
    main()