# main.py
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

import time
import pandas as pd
import numpy as np  # 用于科学均匀抽样
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

# ==================== 性能与防错调优参数 ====================
MAX_TX_FOR_DETAILS = 100          # 深度交互特征抽样上限（兼顾速度与代表性）
MAX_MACRO_SIGS = 6000             # 宏观签名拉取硬上限（6页RPC请求，完美提速）
DETAILS_DELAY = 0.2               # RPC 请求延迟
DETAILS_PROGRESS_BATCH = 50       # 进度打印批次
# ==========================================================

def test_single_address(addr, fetcher, range_start, range_end, idx, total, source_label, source_link, mode):
    log(f"开始测试地址 ({idx}/{total})", addr_idx=idx, addr=addr)

    sigs = []          
    err_map = {}       # 记录每笔宏观交易是否失败
    before = None
    page_limit = 100
    total_fetched = 0
    found_qualified = False
    best_window_info = None   

    ts_start = range_start.timestamp()
    ts_end = range_end.timestamp() if range_end else float('inf')

    effective_limit = 200000 if (mode == 'feb' and not found_qualified) else FETCH_LIMIT

    # ---------- 第一阶段：海量轻量级拉取 (构建宏观时间线) ----------
    while total_fetched < effective_limit and not found_qualified:
        
        # [核心优化] 触发 6000 笔提速硬上限
        if total_fetched >= MAX_MACRO_SIGS:
            log(f"⚡ 达到提速硬上限 ({MAX_MACRO_SIGS}笔)，停止拉取宏观签名。", addr_idx=idx, addr=addr, level="WARNING")
            
            # [尽善尽美的特权机制]：因为能在短时间打满 6000 笔绝对是机器人
            # 豁免它对 MIN_CONTINUOUS_DAYS 的审查，强制构建入围窗口，保送进入 100 笔详情抽样！
            if sigs:
                all_times = [ts for _, ts in sigs]
                actual_start_ts = min(all_times)
                actual_end_ts = max(all_times)
                start_dt = datetime.fromtimestamp(actual_start_ts, timezone.utc)
                end_dt = datetime.fromtimestamp(actual_end_ts, timezone.utc)
                # 哪怕只跑了1小时，也算作1天的活跃度，防止除0错误
                span_days = max(1, (end_dt.date() - start_dt.date()).days + 1) 
                
                best_window_info = (start_dt, end_dt, len(sigs), span_days)
                found_qualified = True
                log(f"🚀 已触发保送机制，强制入围！耗时 {span_days} 天打满 {len(sigs)} 笔交易。", addr_idx=idx, addr=addr)
            break

        try:
            params = [addr, {"limit": page_limit}]
            if before:
                params[1]["before"] = before

            sigs_info = fetcher._make_rpc_call("getSignaturesForAddress", params)
            if not sigs_info:
                break

            page_sigs = []
            for sig in sigs_info:
                block_time = sig.get("blockTime")
                if block_time:
                    page_sigs.append((sig["signature"], block_time))
                    # 0成本提取交易失败状态，用于计算全局 failed_tx_ratio
                    err_map[sig["signature"]] = sig.get("err") is not None

            if not page_sigs:
                break

            page_sigs.reverse()
            sigs = page_sigs + sigs
            total_fetched += len(page_sigs)

            range_sigs = [
                (sig, ts) for sig, ts in sigs
                if ts_start <= ts <= ts_end
            ]

            # 正常情况下的活跃度窗口检验
            if range_sigs and not found_qualified:
                found, start, end, tx_count, max_days = find_best_window_in_range(
                    range_sigs,
                    window_days=MIN_CONTINUOUS_DAYS,
                    min_tx=MIN_TX_IN_WINDOW,
                    range_start=range_start.date(),
                    range_end=range_end.date() if range_end else None
                )
                if found:
                    log(f"✅ 找到符合条件的常规窗口！最长连续 {max_days} 天，相关交易数 = {tx_count}", addr_idx=idx, addr=addr)
                    found_qualified = True
                    best_window_info = (start, end, tx_count, max_days)
                    break

            if sigs and sigs[0][1] < ts_start:
                break

            if len(sigs_info) < page_limit:
                break
            before = sigs_info[-1]["signature"]

        except Exception as e:
            log(f"获取签名出错: {e}", addr_idx=idx, addr=addr, level="ERROR")
            break

    # 兜底校验
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
            else:
                return None
        else:
            return None

    start, end, tx_count, max_days = best_window_info

    range_sigs = [
        (sig, ts) for sig, ts in sigs
        if ts_start <= ts <= ts_end
    ]

    signatures = [sig for sig, _ in range_sigs]
    total_sigs = len(signatures)
    
    # ---------- 第二阶段：微观解耦均匀抽样 (获取深度交互细节) ----------
    if MAX_TX_FOR_DETAILS and total_sigs > MAX_TX_FOR_DETAILS:
        log(f"触发科学分层抽样：从宏观 {total_sigs} 笔中均匀抽取 {MAX_TX_FOR_DETAILS} 笔以获取微观分类特征...", addr_idx=idx, addr=addr)
        # numpy linspace 完美实现从头到尾的均匀覆盖抽样
        indices = np.linspace(0, total_sigs - 1, MAX_TX_FOR_DETAILS, dtype=int)
        signatures_for_details = [signatures[i] for i in indices]
    else:
        signatures_for_details = signatures

    tx_details = []
    batch_size = DETAILS_PROGRESS_BATCH
    total_batches = (len(signatures_for_details) + batch_size - 1) // batch_size
    for i in range(0, len(signatures_for_details), batch_size):
        batch_sigs = signatures_for_details[i:i+batch_size]
        batch_details = fetcher.get_transaction_details_batch(
            batch_sigs,
            delay_per_request=DETAILS_DELAY
        )
        tx_details.extend(batch_details)
        current = len(tx_details)
        log(f"已获取 {current}/{len(signatures_for_details)} 笔微观交易详情 (批次 {i//batch_size+1}/{total_batches})", addr_idx=idx, addr=addr)

    log(f"成功获取 {len(tx_details)} 笔深度详情，准备计算全量分类特征...", addr_idx=idx, addr=addr)

    # ---------- 数据抗毒化保护机制 ----------
    expected_details = len(signatures_for_details)
    actual_details = len(tx_details)
    
    if expected_details > 0 and (actual_details / expected_details) < 0.5:
        log(f"❌ 放弃该地址：RPC 微观详情存活率极低 ({actual_details}/{expected_details})。数据可能被污染！", addr_idx=idx, addr=addr, level="WARNING")
        return None  

    all_times = [ts for _, ts in sigs]
    first_seen = datetime.fromtimestamp(min(all_times), timezone.utc).strftime('%Y-%m-%d')
    last_seen = datetime.fromtimestamp(max(all_times), timezone.utc).strftime('%Y-%m-%d')

    addr_info = {
        'address': addr,
        'source_label': source_label,
        'source_link': source_link,
        'first_seen': first_seen,
        'last_seen': last_seen,
        'active_days': max_days,
        'tx_count_7d': tx_count,
        'total_tx_available': len(sigs)
    }

    # 将宏观失败状态与微观详情一并传入计算器
    features = compute_features(addr, range_sigs, transactions=tx_details, err_map=err_map)
    return addr_info, features

def main():
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

    earliest_allowed = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    mode = MODE

    if mode == 'feb':
        latest_allowed = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)
        log(f"模式：feb（仅限2026年2月内），最早 {earliest_allowed.date()}，最晚 {latest_allowed.date()}")
    elif mode == 'default':
        latest_allowed = None
        log(f"模式：default（从当前时间回溯，窗口起始日期 ≥ {earliest_allowed.date()}）")
    else:
        mode = 'feb'
        latest_allowed = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)

    log(f"开始并发测试地址（并发数=2），目标收集 {TARGET_ADDRESS_COUNT} 个符合条件的地址...")

    fetcher = TransactionFetcher()
    qualified_addresses = []
    features_list = []

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

    df_feat = pd.DataFrame(features_list)
    feat_csv_path = output_dir / 'features.csv'
    df_feat.to_csv(feat_csv_path, index=False)
    log(f"✅ 特征文件已生成: {feat_csv_path}")

if __name__ == "__main__":
    main()