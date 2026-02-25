# src/config.py
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# ==================== Helius RPC 配置 ====================
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_API_KEY:
    raise ValueError("请设置 HELIUS_API_KEY 环境变量，或在 .env 文件中定义")

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# ==================== 地址来源配置 ====================
SOURCE_NAME = "MEV Bot Blackbook"
SOURCE_URL = "https://github.com/outsmartchad/solana-mev-blackbook"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/outsmartchad/Solana-MEV-Bot-Blackbook/main/mev-bot.txt"

# ==================== 筛选条件 ====================
MIN_CONTINUOUS_DAYS = 7
MIN_TX_IN_WINDOW = 1800
FETCH_LIMIT = 5000