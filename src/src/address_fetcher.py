# src/address_fetcher.py
import requests
from pathlib import Path
from .config import GITHUB_RAW_URL, SOURCE_NAME, SOURCE_URL
from .utils import retry

# 本地地址池文件路径（放在项目根目录）
LOCAL_POOL_FILE = Path(__file__).parent.parent / "address_pool.txt"

def read_local_address_pool():
    """从本地文件读取地址池，忽略空行、行首注释（以#开头）和行内注释（#后面的内容），并提取每行的第一个有效token作为地址"""
    if not LOCAL_POOL_FILE.exists():
        return None
    addresses = []
    with open(LOCAL_POOL_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            # 去除首尾空格
            line = line.strip()
            if not line:
                continue
            # 处理行内注释：取第一个 # 之前的部分
            if '#' in line:
                line = line.split('#', 1)[0].strip()
                if not line:
                    continue
            # 按空白字符分割，取第一个token（防止行内有空格）
            parts = line.split()
            if not parts:
                continue
            candidate = parts[0]
            # 可选：简单验证 Solana 地址格式（Base58 长度 32-44）
            if 32 <= len(candidate) <= 44 and all(c in '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz' for c in candidate):
                addresses.append(candidate)
            else:
                print(f"警告：忽略无效地址格式：{candidate}")
    return addresses

@retry(max_retries=3, initial_delay=2)   # 修改此处：delay -> initial_delay
def fetch_from_github():
    """从 GitHub 获取地址列表"""
    resp = requests.get(GITHUB_RAW_URL, timeout=10)
    resp.raise_for_status()
    addresses = [line.strip() for line in resp.text.splitlines() if line.strip()]
    print(f"从 {SOURCE_NAME} 获取到 {len(addresses)} 个候选地址")
    return addresses

def fetch_address_list():
    """获取地址列表：优先从本地文件读取，如果不存在则从 GitHub 获取"""
    local_addrs = read_local_address_pool()
    if local_addrs is not None:
        print(f"从本地文件 address_pool.txt 读取到 {len(local_addrs)} 个地址")
        return local_addrs
    else:
        print("本地文件 address_pool.txt 不存在，尝试从 GitHub 获取...")
        return fetch_from_github()