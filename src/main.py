import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

import time
import pandas as pd
from datetime import datetime, timezone
import concurrent.futures

from src.config import (
    SOURCE_NAME, SOURCE_URL,
    MIN_CONTINUOUS_DAYS, MIN_TX_IN_WINDOW, FETCH_LIMIT,
    TARGET_ADDRESS_COUNT, MODE
)
from src.address_fetcher import fetch_address_list
from src.transaction_fetcher import TransactionFetcher
from src.validator import find_best_window_in_range
from src.feature_calculator import compute_features
from src.logger import log

# ==================== 性能调优参数 ====================
MAX_TX_FOR_DETAILS = 500          # 用于特征计算的交易最大数量（取最近的 N 笔）
DETAILS_DELAY = 1.0               # 每个交易详情请求后的延迟（秒），配合全局限流
DETAILS_PROGRESS_BATCH = 100      # 每获取 100 笔交易详情输出一次进度
# ====================================================

def test_single_address(addr, fetcher, range_start, range_end, idx, total, source_label, source_link, mode):
    """
    测试单个地址。
    - range_start: 允许的最早交易日期（datetime，带时区）
    - range_end:   允许的最晚交易日期（datetime，带时区）；若为 None 则表示无上限
    - mode: 'feb' 或 'default'
    """
    log(f"开始测试地址 ({idx}/{total})", addr_idx=idx, addr=addr)

    # ---------- 分页获取签名，从最新到最旧 ----------
    sigs = []          # 按时间正序存储 (signature, block_time) [旧 -> 新]
    before = None
    page_limit = 100
    total_fetched = 0
    found_qualified = False
    best_window_info = None   # (start, end, tx_count, max_days)

    # 将 range_start 转换为时间戳（用于快速比较）
    ts_start = range_start.timestamp()
    ts_end = range_end.timestamp() if range_end else float('inf')

    # 根据模式确定获取上限：
    # - feb 模式且尚未找到窗口时，需要完整回溯到2月1日之前，因此不设上限（使用一个很大的数）
    # - 其他情况（default模式或已找到窗口）使用 FETCH_LIMIT
    effective_limit = 200000 if (mode == 'feb' and not found_qualified) else FETCH_LIMIT

    while total_fetched < effective_limit and not found_qualified:
        try:
            params = [addr, {"limit": page_limit}]
            if before:
                params[1]["before"] = before

            sigs_info = fetcher._make_rpc_call("getSignaturesForAddress", params)
            if not sigs_info:
                break

            # 处理当前页签名
            page_sigs = []
            for sig in sigs_info:
                block_time = sig.get("blockTime")
                if block_time:
                    page_sigs.append((sig["signature"], block_time))

            if not page_sigs:
                break

            # 将当前页反转（变成从旧到新），插入 sigs 开头
            page_sigs.reverse()
            sigs = page_sigs + sigs
            total_fetched += len(page_sigs)

            # 从已获取的签名中筛选出在 [ts_start, ts_end] 范围内的交易
            range_sigs = [
                (sig, ts) for sig, ts in sigs
                if ts_start <= ts <= ts_end
            ]

            if range_sigs:
                # 在范围内寻找符合条件的连续窗口
                found, start, end, tx_count, max_days = find_best_window_in_range(
                    range_sigs,
                    window_days=MIN_CONTINUOUS_DAYS,
                    min_tx=MIN_TX_IN_WINDOW,
                    range_start=range_start.date(),
                    range_end=range_end.date() if range_end else None
                )
                if found:
                    log(f"✅ 提前找到符合条件的窗口！最长连续 {max_days} 天，7天窗口交易数 = {tx_count} (窗口 {start} 至 {end})", addr_idx=idx, addr=addr)
                    found_qualified = True
                    best_window_info = (start, end, tx_count, max_days)
                    break

            # 如果已回溯到 range_start 之前（即最早签名时间 < ts_start），说明不可能再有新的在范围内的交易
            if sigs and sigs[0][1] < ts_start:
                log(f"已回溯至 {range_start.date()} 之前，停止获取", addr_idx=idx, addr=addr)
                break

            # 准备下一页
            if len(sigs_info) < page_limit:
                break
            before = sigs_info[-1]["signature"]

        except Exception as e:
            log(f"获取签名出错: {e}", addr_idx=idx, addr=addr, level="ERROR")
            break

    # 如果循环结束仍未找到，进行最后一次检查
    if not found_qualified:
        range_sigs_final = [
            (sig, ts) for sig, ts in sigs
            if ts_start <= ts <= ts_end
        ]
        if range_sigs_final:
            found, start, end, tx_count, max_days = find_best_window_in_range(
                range_sigs_final,
                window_days=MIN_CONTINUOUS_DAYS,
                min_tx=MIN_TX_IN_WINDOW,
                range_start=range_start.date(),
                range_end=range_end.date() if range_end else None
            )
            if found:
                found_qualified = True
                best_window_info = (start, end, tx_count, max_days)
                log(f"✅ 最终检查找到符合条件的窗口！最长连续 {max_days} 天，7天窗口交易数 = {tx_count} (窗口 {start} 至 {end})", addr_idx=idx, addr=addr)
            else:
                log(f"不符合条件：最长连续天数 {max_days}，最优窗口交易数 = {tx_count}（需≥{MIN_TX_IN_WINDOW}）", addr_idx=idx, addr=addr)
                return None
        else:
            log(f"{range_start.date()} 之后无交易记录", addr_idx=idx, addr=addr)
            return None

    # ---------- 符合条件，继续处理 ----------
    start, end, tx_count, max_days = best_window_info

    # 获取范围内所有签名（用于特征计算）
    range_sigs = [
        (sig, ts) for sig, ts in sigs
        if ts_start <= ts <= ts_end
    ]

    # 获取交易详情
    signatures = [sig for sig, _ in range_sigs]
    total_sigs = len(signatures)
    log(f"开始获取 {total_sigs} 笔交易的详情（用于特征计算）...", addr_idx=idx, addr=addr)

    if MAX_TX_FOR_DETAILS and total_sigs > MAX_TX_FOR_DETAILS:
        signatures = signatures[:MAX_TX_FOR_DETAILS]
        log(f"限制为最近 {MAX_TX_FOR_DETAILS} 笔交易以加快处理", addr_idx=idx, addr=addr)

    tx_details = []
    batch_size = DETAILS_PROGRESS_BATCH
    total_batches = (len(signatures) + batch_size - 1) // batch_size
    for i in range(0, len(signatures), batch_size):
        batch_sigs = signatures[i:i+batch_size]
        batch_details = fetcher.get_transaction_details_batch(
            batch_sigs,
            delay_per_request=DETAILS_DELAY
        )
        tx_details.extend(batch_details)
        current = len(tx_details)
        log(f"已获取 {current}/{len(signatures)} 笔交易详情 (批次 {i//batch_size+1}/{total_batches})", addr_idx=idx, addr=addr)

    log(f"成功获取 {len(tx_details)} 笔交易详情", addr_idx=idx, addr=addr)

    # 计算首次和最后一次出现（基于全部历史）
    all_times = [ts for _, ts in sigs]
    first_seen = datetime.utcfromtimestamp(min(all_times)).strftime('%Y-%m-%d')
    last_seen = datetime.utcfromtimestamp(max(all_times)).strftime('%Y-%m-%d')
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')

    addr_info = {
        'address': addr,
        'source_label': source_label,
        'source_link': source_link,
        'first_seen': first_seen,
        'last_seen': last_seen,
        'active_days': max_days,
        'tx_count_7d': tx_count,
        'window_start': start_str,
        'window_end': end_str,
        'total_tx_available': len(sigs)
    }

    features = compute_features(addr, range_sigs, transactions=tx_details)
    return addr_info, features


def main():
    # 创建输出目录
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    candidates = fetch_address_list()
    if not candidates:
        log("无法获取地址列表，退出。")
        return

    local_pool_path = Path(__file__).parent / "address_pool.txt"
    using_custom_pool = local_pool_path.exists() and local_pool_path.stat().st_size > 0
    if using_custom_pool:
        source_label = "Custom Address Pool"
        source_link = ""
    else:
        source_label = SOURCE_NAME
        source_link = SOURCE_URL

    # 定义允许的最早日期（2026年2月1日）
    earliest_allowed = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 使用局部变量 mode 处理，避免对导入的 MODE 重新赋值
    mode = MODE

    # 根据模式设置允许的最晚日期
    if mode == 'feb':
        latest_allowed = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)
        log(f"模式：feb（仅限2026年2月内），最早 {earliest_allowed.date()}，最晚 {latest_allowed.date()}")
    elif mode == 'default':
        latest_allowed = None   # 无上限（实际由当前时间自然决定）
        log(f"模式：default（从当前时间回溯，窗口起始日期 ≥ {earliest_allowed.date()}）")
    else:
        log(f"未知模式 {mode}，使用默认 feb 模式")
        mode = 'feb'
        latest_allowed = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)

    log(f"开始并发测试地址（并发数=2），目标收集 {TARGET_ADDRESS_COUNT} 个符合条件的地址...")

    fetcher = TransactionFetcher()
    qualified_addresses = []
    features_list = []

    # 并发数改为 2，加快测试速度（全局限速器确保总请求速率不超过 2 次/秒）
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_addr = {}
        for idx, addr in enumerate(candidates, 1):
            if len(qualified_addresses) >= TARGET_ADDRESS_COUNT:
                break
            future = executor.submit(
                test_single_address,
                addr, fetcher, earliest_allowed, latest_allowed, idx, len(candidates),
                source_label, source_link, mode
            )
            future_to_addr[future] = addr

        for future in concurrent.futures.as_completed(future_to_addr):
            addr = future_to_addr[future]
            try:
                result = future.result()
                if result:
                    addr_info, features = result
                    qualified_addresses.append(addr_info)
                    features_list.append(features)
                    log(f"当前已收集 {len(qualified_addresses)} 个符合条件地址")

                    if len(qualified_addresses) >= TARGET_ADDRESS_COUNT:
                        log(f"已达到目标数量 {TARGET_ADDRESS_COUNT}，取消剩余任务...")
                        for f in future_to_addr:
                            f.cancel()
                        break
            except Exception as e:
                log(f"处理地址 {addr} 时出错: {e}", level="ERROR")

    if not qualified_addresses:
        log("未找到任何符合条件的地址，请检查来源或放宽条件。")
        return

    df_addr = pd.DataFrame(qualified_addresses)
    addr_csv_path = output_dir / 'addresses.csv'
    df_addr.to_csv(addr_csv_path, index=False)
    log(f"✅ addresses.csv 已生成，包含 {len(df_addr)} 个地址 -> {addr_csv_path}")

    df_feat = pd.DataFrame(features_list)
    feat_csv_path = output_dir / 'features.csv'
    df_feat.to_csv(feat_csv_path, index=False)
    log(f"✅ features.csv 已生成，包含 {len(df_feat)} 行特征 -> {feat_csv_path}")

    try:
        log("正在生成分布图...")
        sys.path.append(str(Path(__file__).parent))
        from generate_plots import plot_distributions
        plot_distributions(output_dir)
        log("✅ 分布图已生成")
    except ImportError as e:
        log(f"⚠️ 未找到 generate_plots.py 或缺少绘图库，跳过图表生成。({e})")
    except Exception as e:
        log(f"⚠️ 生成图表时出错: {e}")


if __name__ == "__main__":
    main()