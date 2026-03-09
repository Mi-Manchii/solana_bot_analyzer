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
ADDRESS_SOURCES = [
    {
        "name": "MEV Bot Blackbook",
        "url": "https://raw.githubusercontent.com/outsmartchad/Solana-MEV-Bot-Blackbook/main/mev-bot.txt"
    },
    # {
    #     "name": "Another Bot List",
    #     "url": "https://raw.githubusercontent.com/username/repo/main/bots.txt"
    # },
]

# 保留单来源变量
SOURCE_NAME = ADDRESS_SOURCES[0]["name"]   # 使用第一个来源的名称
SOURCE_URL = ADDRESS_SOURCES[0]["url"]     # 使用第一个来源的链接
GITHUB_RAW_URL = ADDRESS_SOURCES[0]["url"]

# ==================== 筛选条件 ====================
MIN_CONTINUOUS_DAYS = 7
MIN_TX_IN_WINDOW = 1800
FETCH_LIMIT = 50000

# ==================== 目标收集数量 ====================
TARGET_ADDRESS_COUNT = 100   # 可根据需要调整（最低50，目标100）

# ==================== 模式选择 ====================
# 'feb' : 窗口限定在 2026年2月内
# 'default' : 从当前时间回溯，窗口起始日期 ≥ 2026年2月1日
MODE = os.getenv("MODE", "default")   # 默认 feb