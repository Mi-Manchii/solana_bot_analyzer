# Solana Bot 地址采集与分析（第一阶段）

## 项目目标
从公开数据源获取一个Solana机器人地址，验证其满足连续7天活跃且7天内交易数≥2000，并生成行为特征CSV。

## 数据源
1. 地址来源：MEV Bot Blackbook
一个公开维护的 Solana MEV 机器人地址黑名单，包含 20+ 已知机器人地址。
2. 交易数据：Helius RPC
使用高性能 Solana RPC 节点，直接通过 HTTP API 获取地址的签名历史，包含 blockTime 字段用于日期统计。

## 项目结构
.
├── main.py
├── src/
│ ├── init.py
│ ├── config.py
│ ├── address_fetcher.py
│ ├── transaction_fetcher.py
│ ├── validator.py
│ ├── feature_calculator.py
│ └── utils.py
├── requirements.txt
└── README.md

## 运行方法
1. 安装依赖：`pip install -r requirements.txt`
2. 执行主程序：`python main.py`

## 执行采集
在项目根目录运行：
python main.py
程序将自动：
1. 从 GitHub 获取候选地址列表
2. 依次查询每个地址的签名历史（默认最多 4000 条）
3. 筛选满足连续活跃 ≥7 天且某连续 7 天窗口内交易数 ≥1800 的第一个地址
4. 生成 addresses.csv 和 features.csv

## 输出文件
- `addresses.csv`
- `features.csv`


## 注意事项
- 确保网络畅通，可访问GitHub和Solana RPC。
- 若使用公共RPC遇到限流，可考虑更换为Helius节点（修改`src/config.py`中的`RPC_URL`）。
