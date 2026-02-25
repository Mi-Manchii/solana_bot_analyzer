# src/transaction_fetcher.py
import requests
import time
from .config import RPC_URL
from .utils import retry

class TransactionFetcher:
    def __init__(self, rpc_url=RPC_URL):
        self.rpc_url = rpc_url
        self.session = requests.Session()

    @retry(max_retries=3, delay=2)
    def _make_rpc_call(self, method, params):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        resp = self.session.post(self.rpc_url, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            raise Exception(f"RPC 错误: {result['error']}")
        return result.get("result")

    def get_signatures_with_time(self, address, limit=3000):
        """
        获取地址的签名列表，返回 [(signature, block_time), ...]
        """
        all_sigs = []
        before = None
        page_limit = 100

        while len(all_sigs) < limit:
            try:
                params = [address, {"limit": page_limit}]
                if before:
                    params[1]["before"] = before

                sigs_info = self._make_rpc_call("getSignaturesForAddress", params)
                if not sigs_info:
                    break

                for sig in sigs_info:
                    if sig.get("blockTime"):
                        all_sigs.append((sig["signature"], sig["blockTime"]))

                if len(sigs_info) < page_limit:
                    break

                before = sigs_info[-1]["signature"]
                time.sleep(0.2)  # 控制请求频率
            except Exception as e:
                print(f"获取签名出错: {e}")
                break

        return all_sigs