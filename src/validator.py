# src/validator.py
from collections import defaultdict
from datetime import timedelta
from .utils import timestamp_to_date

def find_best_window_in_range(sigs_with_time, window_days=7, min_tx=1800, range_start=None, range_end=None):
    """
    在指定的日期范围内寻找连续 window_days 天且交易总数 >= min_tx 的窗口。
    返回 (found, start_date, end_date, tx_count, max_streak_days)
    - found: bool 是否找到
    - start_date: 窗口起始日期
    - end_date: 窗口结束日期
    - tx_count: 窗口内总交易数
    - max_streak_days: 范围内最长连续天数（可能小于 window_days）
    """
    if not sigs_with_time:
        return False, None, None, 0, 0

    # 统计每日交易数
    daily_count = defaultdict(int)
    for _, ts in sigs_with_time:
        date = timestamp_to_date(ts)
        # 如果指定了范围，只统计范围内的日期
        if range_start and date < range_start:
            continue
        if range_end and date > range_end:
            continue
        daily_count[date] += 1

    dates = sorted(daily_count.keys())
    if len(dates) < window_days:
        # 计算最长连续天数
        max_streak = 1
        current_streak = 1
        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 1
        return False, None, None, 0, max_streak if dates else 0

    # 寻找最长连续天数（用于返回）
    max_streak = 1
    current_streak = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 1

    # 在连续段内滑动窗口（只考虑窗口所有日期都在范围内）
    best_tx = 0
    best_start = None
    best_end = None

    # 使用滑动窗口检查所有可能的连续7天窗口
    # 将日期转换为连续的索引，因为dates可能不是连续的
    # 我们只考虑dates中连续的部分
    i = 0
    while i <= len(dates) - window_days:
        # 检查从i开始的 window_days 个日期是否连续
        is_continuous = True
        for j in range(i, i + window_days - 1):
            if (dates[j+1] - dates[j]).days != 1:
                is_continuous = False
                break
        if is_continuous:
            window_dates = dates[i:i+window_days]
            tx_sum = sum(daily_count[d] for d in window_dates)
            if tx_sum >= min_tx and tx_sum > best_tx:
                best_tx = tx_sum
                best_start = window_dates[0]
                best_end = window_dates[-1]
            i += 1  # 正常滑动
        else:
            # 找到下一个可能的连续起点
            # 找到不连续的位置
            for j in range(i, i + window_days - 1):
                if (dates[j+1] - dates[j]).days != 1:
                    i = j + 1
                    break
            else:
                i += 1

    if best_tx >= min_tx:
        return True, best_start, best_end, best_tx, max_streak
    else:
        return False, None, None, best_tx, max_streak