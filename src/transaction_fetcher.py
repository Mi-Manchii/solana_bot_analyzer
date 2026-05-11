# src/transaction_fetcher.py
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .logger import log
from .config import RPC_NODES

class TransactionFetcher:
    def __init__(self, rpc_nodes=None):
        self.rpc_nodes = rpc_nodes if rpc_nodes else RPC_NODES
        self.current_node_index = 0
        
        # [核心优化] 使用 Session 保持 HTTP 长连接，提速并防 10054 错误
        self.session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

    def _get_current_rpc(self):
        return self.rpc_nodes[self.current_node_index]

    def _rotate_rpc(self):
        if len(self.rpc_nodes) > 1:
            self.current_node_index = (self.current_node_index + 1) % len(self.rpc_nodes)
            log(f"RPC 节点切换至: {self._get_current_rpc()[:30]}...", level="INFO")

    def _make_rpc_call(self, method, params, retries=5):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        for attempt in range(retries):
            rpc_url = self._get_current_rpc()
            try:
                response = self.session.post(rpc_url, json=payload, timeout=15)
                
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    log(f"RPC 被限流 (429)，等待 {wait_time} 秒后重试...", level="WARNING")
                    time.sleep(wait_time)
                    self._rotate_rpc()
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    log(f"RPC 错误 [{method}]: {data['error']}", level="ERROR")
                    return None
                    
                return data.get("result")
                
            except requests.exceptions.RequestException as e:
                wait_time = 2 ** attempt
                log(f"RPC 请求异常: {e}. 等待 {wait_time} 秒后重试...", level="ERROR")
                time.sleep(wait_time)
                self._rotate_rpc()
                
        log(f"❌ 超过最大重试次数，放弃当前 RPC 请求: {method}", level="ERROR")
        return None

    def _parse_transaction(self, tx_data):
        """深度解析交易特征，精准提取优先费与账户列表"""
        if not tx_data or not isinstance(tx_data, dict):
            return {}

        meta = tx_data.get("meta") or {}
        transaction = tx_data.get("transaction") or {}
        message = transaction.get("message") or {}

        # ==========================================================
        # 1. 提取静态与动态账号列表 (兼容 V0 和 Legacy 格式)
        # ==========================================================
        account_keys = []
        raw_keys = message.get("accountKeys", [])
        for key in raw_keys:
            if isinstance(key, dict):  # v0 格式
                account_keys.append(key.get("pubkey", ""))
            else:  # legacy 格式
                account_keys.append(str(key))

        # [顶级修复] 提取 V0 交易中的 Address Lookup Table (ALT) 动态账户
        # 捕获高级 MEV 机器人 Jito 小费的核心防线！
        loaded_addresses = meta.get("loadedAddresses", {})
        if loaded_addresses:
            account_keys.extend(loaded_addresses.get("writable", []))
            account_keys.extend(loaded_addresses.get("readonly", []))

        # ==========================================================
        # 2. 提取涉及的 Program IDs
        # ==========================================================
        program_ids = set()
        instructions = message.get("instructions", [])
        for ix in instructions:
            pid_idx = ix.get("programIdIndex")
            if pid_idx is not None and pid_idx < len(account_keys):
                program_ids.add(account_keys[pid_idx])
            elif "programId" in ix:
                 program_ids.add(ix["programId"])

        # ==========================================================
        # 3. [核心修复] 计算真实的优先费 (Priority Fee)
        # ==========================================================
        signatures = transaction.get("signatures", [])
        # Solana 基础签名费为 5000 lamports/签名
        base_fee = len(signatures) * 5000 if signatures else 5000
        total_fee = meta.get("fee", 0)
        
        # 优先费 = 总费 - 基础费
        priority_fee = max(0, total_fee - base_fee)
        
        # [修复笔误] 必须是确切的 ComputeBudget 官方程序 ID
        COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
        logs = meta.get("logMessages", [])
        has_compute_budget = any("ComputeBudgetProgram" in log for log in logs) if logs else False
        
        if not has_compute_budget and COMPUTE_BUDGET_PROGRAM not in program_ids:
             priority_fee = 0 

        # ==========================================================
        # 4. 代币提取
        # ==========================================================
        tokens = set()
        for balance in meta.get("preTokenBalances", []) + meta.get("postTokenBalances", []):
            mint = balance.get("mint")
            if mint:
                tokens.add(mint)

        return {
            "signature": signatures[0] if signatures else None,
            "fee_lamports": total_fee,
            "priority_fee_lamports": priority_fee,
            "compute_units_consumed": meta.get("computeUnitsConsumed", 0),
            "account_keys": account_keys,
            "program_ids": list(program_ids),
            "tokens": list(tokens),
            "instruction_count": len(instructions),
            "instruction_programs": list(program_ids) 
        }

    def get_transaction_details_batch(self, signatures, delay_per_request=0):
        results = []
        for sig in signatures:
            # maxSupportedTransactionVersion=0 确保能兼容拉取 v0 交易
            tx_data = self._make_rpc_call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if tx_data:
                parsed_data = self._parse_transaction(tx_data)
                if parsed_data:
                    results.append(parsed_data)
            if delay_per_request > 0:
                time.sleep(delay_per_request)
        return results