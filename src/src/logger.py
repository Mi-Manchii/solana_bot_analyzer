# src/logger.py
from datetime import datetime
import sys

def log(msg, addr_idx=None, addr=None, level="INFO"):
    """
    输出带时间戳的日志，可选包含地址索引和地址缩写。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{timestamp}]"
    if addr_idx is not None:
        prefix += f"[{addr_idx}]"
    if addr is not None:
        # 取地址前6位和后4位作为缩写
        short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        prefix += f"[{short_addr}]"
    print(f"{prefix} {level}: {msg}", flush=True)