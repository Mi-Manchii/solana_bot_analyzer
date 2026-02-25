# address_fetcher.py
import requests
from .config import GITHUB_RAW_URL, SOURCE_NAME, SOURCE_URL
from .utils import retry

@retry(max_retries=3, delay=2)
def fetch_address_list():
    resp = requests.get(GITHUB_RAW_URL, timeout=10)
    resp.raise_for_status()
    addresses = [line.strip() for line in resp.text.splitlines() if line.strip()]
    print(f"从 {SOURCE_NAME} 获取到 {len(addresses)} 个候选地址")
    return addresses