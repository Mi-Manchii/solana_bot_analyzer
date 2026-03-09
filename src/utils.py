# src/utils.py
import time
import functools
import random
from datetime import datetime
from threading import Lock

# ==================== 重试装饰器（原有） ====================
def retry(max_retries=5, initial_delay=1, backoff_factor=2, jitter=True, exceptions=(Exception,)):
    """
    带指数退避和抖动的重试装饰器。
    :param max_retries: 最大重试次数
    :param initial_delay: 初始延迟（秒）
    :param backoff_factor: 退避因子，每次重试延迟乘以该值
    :param jitter: 是否添加随机抖动（±0.5秒）
    :param exceptions: 需要重试的异常类型
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries - 1:
                        raise
                    # 计算带抖动的延迟
                    sleep_time = delay
                    if jitter:
                        sleep_time += random.uniform(-0.5, 0.5)
                        sleep_time = max(0.1, sleep_time)  # 确保非负
                    print(f"重试 {attempt+1}/{max_retries} 次，错误: {e}，等待 {sleep_time:.2f} 秒后重试")
                    time.sleep(sleep_time)
                    delay *= backoff_factor
            return None  # 理论上不会执行到这里
        return wrapper
    return decorator

def timestamp_to_date(ts):
    return datetime.utcfromtimestamp(ts).date()

# ==================== 新增：全局速率限制器 ====================
class RateLimiter:
    """线程安全的速率限制器，限制每秒调用次数"""
    def __init__(self, calls_per_second=2):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
        self.lock = Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()

# 创建全局限流器（可根据需要调整速率）
_rate_limiter = RateLimiter(calls_per_second=2)

def rate_limited(func):
    """装饰器：在调用函数前等待以满足速率限制"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _rate_limiter.wait()
        return func(*args, **kwargs)
    return wrapper