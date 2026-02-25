# validator.py
from collections import defaultdict
from datetime import timedelta
from .utils import timestamp_to_date

def find_best_continuous_window(sigs_with_time):
    if not sigs_with_time:
        return False, None, None, 0, 0

    daily_count = defaultdict(int)
    for _, ts in sigs_with_time:
        date = timestamp_to_date(ts)
        daily_count[date] += 1

    dates = sorted(daily_count.keys())
    if len(dates) < 7:
        return False, None, None, 0, len(dates)

    max_streak = 1
    current_streak = 1
    best_streak_start = dates[0]
    best_streak_end = dates[0]

    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
                best_streak_start = dates[i - current_streak + 1]
                best_streak_end = dates[i]
        else:
            current_streak = 1

    if max_streak < 7:
        return False, None, None, 0, max_streak

    window_end = best_streak_end
    window_start = window_end - timedelta(days=6)

    tx_in_window = sum(
        count for date, count in daily_count.items()
        if window_start <= date <= window_end
    )

    return True, window_start, window_end, tx_in_window, max_streak