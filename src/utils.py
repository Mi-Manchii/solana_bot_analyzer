# utils.py
import time
import functools
from datetime import datetime

def retry(max_retries=3, delay=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise
                    print(f"重试 {i+1}/{max_retries} 次，错误: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

def timestamp_to_date(ts):
    return datetime.utcfromtimestamp(ts).date()