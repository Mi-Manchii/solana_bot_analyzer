# src/transaction_fetcher.py
import requests
import time
from .config import RPC_URL
from .utils import retry, rate_limited   # 导入限流装饰器


COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"


def _pubkey(value):
    if isinstance(value, dict):
        return value.get("pubkey")
    return value


class TransactionFetcher:
    def __init__(self, rpc_url=RPC_URL):
        self.rpc_url = rpc_url
        self.session = requests.Session()

    @rate_limited   # 新增：所有RPC调用前等待
    @retry(max_retries=5, initial_delay=2, backoff_factor=2, jitter=True, exceptions=(requests.RequestException, Exception))
    def _make_rpc_call(self, method, params):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        resp = self.session.post(self.rpc_url, json=payload, timeout=30)
        
        # 处理429或5xx错误，触发重试
        if resp.status_code in (429, 502, 503, 504):
            raise Exception(f"Server error {resp.status_code}")
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
                # 原有 sleep 可以移除，因为限流装饰器已控制整体速率
                # time.sleep(0.2)
            except Exception as e:
                print(f"获取签名出错: {e}")
                break

        return all_sigs

    @retry(max_retries=2, initial_delay=1, backoff_factor=2, jitter=True)
    def get_transaction_details(self, signature):
        """
        获取单笔交易的详细信息，用于提取程序ID和代币信息。
        返回解析后的字典，包含程序ID列表和代币Mint列表。
        """
        result = self._make_rpc_call("getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return None

        # 提取程序ID列表、指令数量和优先费用相关信息。
        program_ids = set()
        instruction_programs = []
        instruction_types = []
        compute_unit_price = 0
        instruction_count = 0
        try:
            msg = result['transaction']['message']
            account_keys = msg['accountKeys']
            for ix in msg.get('instructions', []):
                instruction_count += 1
                program_id = None
                if 'programIdIndex' in ix:
                    prog_idx = ix['programIdIndex']
                    if prog_idx < len(account_keys):
                        program_id = _pubkey(account_keys[prog_idx])
                elif 'programId' in ix:
                    program_id = _pubkey(ix['programId'])
                if program_id:
                    program_ids.add(program_id)
                    instruction_programs.append(program_id)
                if ix.get('program'):
                    instruction_types.append(str(ix.get('program')))
                parsed = ix.get('parsed') if isinstance(ix, dict) else None
                if program_id == COMPUTE_BUDGET_PROGRAM_ID and isinstance(parsed, dict):
                    info = parsed.get('info', {})
                    if parsed.get('type') == 'setComputeUnitPrice':
                        compute_unit_price = int(info.get('microLamports', 0) or 0)
        except (KeyError, IndexError):
            pass

        # 提取代币Mint列表（从 preTokenBalances / postTokenBalances）
        tokens = set()
        try:
            meta = result.get('meta', {})
            for bal_list in [meta.get('preTokenBalances', []), meta.get('postTokenBalances', [])]:
                for bal in bal_list:
                    if 'mint' in bal:
                        tokens.add(bal['mint'])
        except Exception:
            pass

        meta = result.get('meta') or {}
        fee_lamports = int(meta.get('fee', 0) or 0)
        compute_units = int(meta.get('computeUnitsConsumed', 0) or 0)
        priority_fee_lamports = 0
        if compute_unit_price and compute_units:
            priority_fee_lamports = (compute_unit_price * compute_units) / 1_000_000

        return {
            'signature': signature,
            'program_ids': list(program_ids),
            'tokens': list(tokens),
            'block_time': result.get('blockTime'),
            'fee_lamports': fee_lamports,
            'priority_fee_lamports': priority_fee_lamports,
            'compute_units_consumed': compute_units,
            'compute_unit_price_micro_lamports': compute_unit_price,
            'instruction_count': instruction_count,
            'instruction_programs': instruction_programs,
            'instruction_types': instruction_types,
        }

    # 修改：改为纯串行获取，避免并发导致速率不可控
    def get_transaction_details_batch(self, signatures, delay_per_request=1.0):
        """
        串行获取多笔交易详情，每个请求后等待固定延迟。
        delay_per_request: 每个请求后的等待时间（秒），建议 ≥ 1.0
        """
        details = []
        total = len(signatures)
        for i, sig in enumerate(signatures, 1):
            try:
                res = self.get_transaction_details(sig)
                if res:
                    details.append(res)
            except Exception as e:
                print(f"获取交易 {sig} 详情失败: {e}")
            if i < total:
                time.sleep(delay_per_request)
        return details
