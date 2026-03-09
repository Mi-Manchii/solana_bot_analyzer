# Solana Bot Address Analyzer

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📌 项目简介
本项目旨在从公开数据源中识别 **Solana 链上可能为自动化程序（机器人）的高频交易地址**，并对其行为进行量化特征分析。通过自动获取地址的历史交易签名，筛选出在指定时间段内（默认 **2026年2月**）满足 **连续7天活跃且7天内交易数 ≥1800** 的地址，最终生成包含基础信息和多维行为特征的 CSV 文件，以及特征分布可视化图表。

该工具可作为区块链地址画像、链上行为分析、MEV 研究等领域的基础设施。

## 🎯 项目目标
- 从公开机器人地址列表（如 MEV Bot Blackbook）或用户自定义文件中获取候选地址。
- 自动扫描每个地址在 **2026年2月** 内的交易历史，确保数据完整性。
- 筛选出满足以下条件的地址：
  - 在2月内存在至少一个 **连续7天** 的窗口；
  - 该窗口内的总交易数 **≥1800** 笔。
- 为每个符合条件的地址计算 **22项行为特征**，涵盖活跃度、时间规律、交互多样性三大维度。
- 输出 `addresses.csv` 和 `features.csv`，并生成特征分布图（PNG/PDF）。
- 提供一键运行脚本，确保结果可复现。

## 🔗 数据源
- **候选地址**：
  - 默认从 GitHub 项目 [Solana-MEV-Bot-Blackbook](https://github.com/outsmartchad/Solana-MEV-Bot-Blackbook) 获取（社区维护的疑似机器人列表）。
  - 支持用户通过本地文件 `address_pool.txt` 提供自定义地址（每行一个，支持 `#` 注释）。
- **链上数据**：
  - 通过 [Helius RPC](https://helius.xyz) 获取地址的签名历史及交易详情。需自行申请 API Key。

## 📁 项目结构

```text
.
├── main.py                 # 主程序入口
├── run.sh                  # Linux/macOS 一键运行脚本
├── run.bat                 # Windows 一键运行脚本
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── address_pool.txt.example # 自定义地址池示例
├── src/
│   ├── __init__.py
│   ├── config.py           # 配置参数（RPC、阈值、模式等）
│   ├── address_fetcher.py  # 从本地或GitHub获取地址
│   ├── transaction_fetcher.py # RPC调用封装（含限流与重试）
│   ├── validator.py        # 连续窗口检测算法
│   ├── feature_calculator.py # 22项特征计算
│   ├── logger.py           # 带时间戳的日志
│   └── utils.py            # 重试装饰器、速率限制器
└── generate_plots.py       # 可视化生成（分布图、热力图）
```

## ⚙️ 安装与配置

### 环境要求
- Python 3.9 或更高版本
- 依赖库：`requests`, `pandas`, `matplotlib`, `seaborn`, `python-dotenv`

### 安装步骤

1. **克隆本仓库**：
   ```bash
   git clone https://github.com/yourname/solana-bot-analyzer.git
   cd solana-bot-analyzer

2. **安装依赖**：
   ```bash
   pip install -r requirements.txt

### 配置 Helius API Key

复制 `.env.example` 为 `.env`，并填入您的 API Key：

```text
HELIUS_API_KEY=your_helius_api_key_here
```

## 🚀 运行方法

### 一键运行（推荐）
- **Linux/macOS**：
  ```bash
  chmod +x run.sh
  ./run.sh

- **Windows**：
- 双击 run.bat 或在命令行中执行。

### 手动运行

  ```bash
  python main.py
  ```

## ⚡ 运行模式说明

通过 `config.py` 中的 `MODE` 变量（或 `.env` 文件）可选择两种分析模式：

| 模式 | 描述 |
| :--- | :--- |
| **feb** | 限定在2026年2月内寻找窗口（默认）。程序会完整回溯至2月1日之前，确保2月数据完整。 |
| **default** | 从当前时间回溯，寻找任意连续7天窗口（起始日期 ≥ 2026年2月1日），找到即停止，速度更快。 |

## 📊 输出文件

所有输出均保存在项目根目录的 `output/` 文件夹下：

| 文件 | 描述 |
| :--- | :--- |
| `addresses.csv` | 符合条件的地址列表，包含来源、首次/最后出现时间、最佳窗口信息等。 |
| `features.csv` | 每个地址的22项行为特征（见下文特征列表）。 |
| `feature_distributions.png/pdf` | 基础特征（日均交易、夜间比例等）分布图。 |
| `new_feature_distributions.png/pdf` | 多样性特征（程序种类、代币熵等）分布图。 |
| `feature_correlation.png/pdf` | 所有数值特征的相关性热力图。 |
