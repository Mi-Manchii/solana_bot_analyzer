# Solana Bot 地址采集与分析（第一阶段）

## 项目目标
从公开数据源和本地地址池获取 Solana MEV 机器人候选地址，验证其满足连续7天活跃且7天内交易数≥1800，并生成面向论文实验的行为特征CSV。

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
4. 生成 addresses.csv 和 features.csv，其中包含基础活跃度、时间规律、交互多样性、优先费用和指令级复杂度等特征

## 输出文件
- `addresses.csv`
- `features.csv`
- `features_v2.csv`（与 `features.csv` 同源，便于论文中按增强特征集引用）

## 论文实验增强流程

前期采集完成后，可以直接运行离线实验：

```bash
python run_paper_experiments.py
```

该脚本会基于 `output/features.csv` 依次生成：

- `heuristic_scores.csv`：启发式规则 baseline，对每个地址给出规则命中情况、机器人评分和置信度；
- `heuristic_summary.csv`：启发式评分的描述统计；
- `cluster_assignments.csv`：KMeans 聚类分型结果，每个地址对应一个行为簇；
- `cluster_profile.csv` / `cluster_profile_cn.csv`：每个簇的均值画像和自动推断类型；
- `gmm_cluster_assignments.csv` / `gmm_cluster_profile.csv`：GMM 聚类结果，用于补充论文中的行为分型实验；
- `dbscan_cluster_assignments.csv`：DBSCAN 密度聚类结果，用于识别离群或小簇地址；
- `cluster_k_scores.csv`：不同 K 值的轮廓系数，用于说明聚类数选择；
- `cluster_pca.png` / `cluster_pca.pdf`：PCA 二维投影聚类图；
- `case_candidates.csv` / `case_candidates_cn.csv`：可写入论文的典型地址候选；
- 若存在 `output/features_labeled.csv`，还会训练监督学习模型并输出 `model_cv_metrics.csv`、`ablation_metrics.csv`、`classification_report.json`、`confusion_matrix.png`、`feature_importance.csv`、`feature_importance.png` 和 `best_model.joblib`。

### 监督学习数据格式

当前已有 `output/features.csv` 主要是疑似机器人正样本。若要训练“机器人/普通用户”二分类模型，需要额外准备负样本，并合并成：

```text
output/features_labeled.csv
```

其中必须包含：

```csv
address,label,...
疑似机器人地址,1,...
普通用户地址,0,...
```

如果暂时没有负样本，`run_paper_experiments.py` 会自动跳过监督学习，但仍会完成启发式 baseline、无监督聚类和案例导出。这些内容可以支撑论文中的“前期实验基础”“机器人行为分型”和“典型案例分析”部分。

### 已对齐开题报告的 Solana 特征

当前采集脚本会在获取交易详情时解析 `fee`、`computeUnitsConsumed`、Compute Budget 优先费用、交易指令数量、指令程序分布、核心 DEX 程序交互、Pump.fun 程序交互和低复用代币交互比例。重新运行 `python main.py` 后，新生成的 `features.csv` 会包含 `avg_priority_fee_lamports`、`priority_fee_cv`、`avg_instruction_count`、`instruction_program_entropy`、`core_dex_interaction_ratio`、`pump_fun_interaction_ratio`、`new_token_interaction_ratio` 等列，用于支撑开题报告中的“Solana 特有特征”“行为分型”和“消融实验”。


## 注意事项
- 确保网络畅通，可访问GitHub和Solana RPC。
- 若使用公共RPC遇到限流，可考虑更换为Helius节点（修改`src/config.py`中的`RPC_URL`）。
