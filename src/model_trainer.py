import json
import joblib
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.mixture import GaussianMixture
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report, 
    ConfusionMatrixDisplay, 
    accuracy_score, 
    f1_score
)
from sklearn.model_selection import (
    StratifiedKFold, 
    cross_validate, 
    cross_val_predict
)

# 导入项目中已有的工具函数
from paper_utils import (
    ensure_output_dir, 
    load_features, 
    numeric_feature_columns, 
    save_dataframe
)

# 对应开题报告表 2.1 的特征体系分组
FEATURE_GROUPS = {
    "activity": ["total_transactions", "unique_days", "avg_tx_per_day", "max_tx_in_day"],
    "time": [
        "night_ratio", "weekend_ratio", "avg_interval_seconds", 
        "median_interval_seconds", "std_interval_seconds", "cv_interval", 
        "hourly_entropy", "daily_cv", "max_inactive_days"
    ],
    "interaction": ["unique_programs", "program_entropy", "unique_tokens", "token_entropy"],
    "solana_specific": [
        "avg_priority_fee_lamports", "priority_fee_cv", "priority_fee_nonzero_ratio",
        "avg_compute_units", "avg_instruction_count", "instruction_program_entropy",
        "instruction_type_entropy", "core_dex_interaction_ratio", 
        "pump_fun_interaction_ratio", "new_token_interaction_ratio"
    ],
}

def make_supervised_models():
    """构建开题报告提到的监督学习集成模型"""
    models = {
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            # [性能优化]: n_jobs=-1 开启底层随机森林的多核训练
            ("model", RandomForestClassifier(n_estimators=400, class_weight="balanced", random_state=42, n_jobs=-1))
        ]),
        "hist_gradient_boosting": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", HistGradientBoostingClassifier(max_iter=250, random_state=42))
        ])
    }
    # 尝试加载 XGBoost
    try:
        from xgboost import XGBClassifier
        models["xgboost"] = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            # [性能优化]: n_jobs=-1 开启 XGBoost 的多核训练
            ("model", XGBClassifier(n_estimators=300, learning_rate=0.05, random_state=42, n_jobs=-1))
        ])
    except ImportError: pass
    return models

def run_heuristic_baseline(df, output_dir):
    """
    实现开题报告 2.4 节要求的启发式规则基线。
    规则逻辑：高频交易 + 专注特定程序 + 积极支付优先费用。
    """
    print("正在运行启发式规则基线...")
    preds = []
    for _, row in df.iterrows():
        # 基于前期实验积累的阈值
        is_bot = (
            (row.get('avg_tx_per_day', 0) > 200) and 
            (row.get('unique_programs', 10) <= 5) and
            (row.get('priority_fee_nonzero_ratio', 0) > 0.4)
        )
        preds.append(1 if is_bot else 0)
    
    df['heuristic_pred'] = preds
    if "label" in df.columns:
        y_true = pd.to_numeric(df["label"]).astype(int)
        report = classification_report(y_true, preds, output_dict=True, zero_division=0)
        save_dataframe(pd.DataFrame(report).T, output_dir / "heuristic_report.csv")
        print(f"启发式基线准确率: {report['accuracy']:.4f}")
    return preds

def run_unsupervised_clustering(output_dir, feature_file="features.csv", n_clusters=3):
    """
    实现开题报告第四阶段要求的行为分型探索。
    使用 GMM 和 DBSCAN 识别机器人亚型（狙击、套利等）。
    """
    print(f"正在对 {feature_file} 进行无监督聚类探索...")
    df = load_features(output_dir, feature_file)
    cols = numeric_feature_columns(df)
    
    # 预处理：填补缺失值并标准化
    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler())
    ])
    x_scaled = pipe.fit_transform(df[cols])

    # 1. 高斯混合模型 (GMM) - 用于概率分型
    gmm = GaussianMixture(n_components=n_clusters, random_state=42)
    df['gmm_cluster'] = gmm.fit_predict(x_scaled)

    # 2. 聚类特征均值分析 (用于解释亚型行为)
    cluster_means = df.groupby('gmm_cluster')[cols].mean()
    save_dataframe(cluster_means, output_dir / "cluster_behavior_analysis.csv")

    # 3. PCA 降维可视化
    pca = PCA(n_components=2)
    components = pca.fit_transform(x_scaled)
    df['pca_1'], df['pca_2'] = components[:, 0], components[:, 1]

    plt.figure(figsize=(10, 7))
    sns.scatterplot(data=df, x='pca_1', y='pca_2', hue='gmm_cluster', palette='Set1', s=60)
    plt.title("Solana Bot Behavior Clustering (PCA)")
    plt.savefig(output_dir / "behavior_clusters.png", dpi=200)
    plt.close()

    save_dataframe(df, output_dir / "features_with_clusters.csv")
    print("聚类分析完成，已生成亚型行为特征对比表。")

def train_supervised(output_dir, feature_file="features_labeled.csv"):
    """
    执行监督学习训练、交叉验证及消融实验。
    """
    output_dir = ensure_output_dir(output_dir)
    feature_path = output_dir / feature_file
    if not feature_path.exists():
        print(f"跳过监督学习：未找到标注数据 {feature_file}")
        return

    df = load_features(output_dir, feature_file)
    y = pd.to_numeric(df["label"]).astype(int)
    x = df[numeric_feature_columns(df)]
    cols = x.columns.tolist()

    # 1. 模型性能对比
    # 将 5 改为 2，或者使用 LeaveOneOut (不推荐，最好还是加数据)
    cv = StratifiedKFold(n_splits=2, shuffle=True, random_state=42)
    best_model_name = None
    max_f1 = -1
    
    results = []
    print("正在执行交叉验证模型评估...")
    for name, model in make_supervised_models().items():
        # [性能优化]: n_jobs=-1 开启交叉验证评估的并发计算
        scores = cross_validate(model, x, y, cv=cv, scoring=['accuracy', 'f1', 'precision', 'recall'], n_jobs=-1)
        res = {"model": name}
        for k, v in scores.items():
            if k.startswith("test_"): res[k[5:]] = v.mean()
        results.append(res)
        if res['f1'] > max_f1:
            max_f1, best_model_name = res['f1'], name

    save_dataframe(pd.DataFrame(results), output_dir / "supervised_comparison.csv")

    # 2. 运行消融实验
    print("运行消融实验验证 Solana 特有特征贡献 (此步骤可能需要几十秒)...")
    ablation_results = []
    # 全部特征作为基准
    base_model = make_supervised_models()["random_forest"]
    
    # [性能优化]: n_jobs=-1 开启基准模型交叉验证的并发计算
    full_f1 = cross_validate(base_model, x, y, cv=cv, scoring='f1', n_jobs=-1)['test_score'].mean()
    ablation_results.append({"setting": "All Features", "f1": full_f1, "drop": 0})

    for group_name, group_cols in FEATURE_GROUPS.items():
        # 移除该组特征
        remaining_cols = [c for c in cols if c not in group_cols]
        if remaining_cols:
            # [性能优化]: n_jobs=-1 开启特征移除后的交叉验证并发计算
            f1 = cross_validate(base_model, x[remaining_cols], y, cv=cv, scoring='f1', n_jobs=-1)['test_score'].mean()
            ablation_results.append({
                "setting": f"Without {group_name}", 
                "f1": f1, 
                "drop": full_f1 - f1
            })
    save_dataframe(pd.DataFrame(ablation_results), output_dir / "ablation_study.csv")

    # 3. 最终模型训练与特征重要性
    print(f"训练最终模型: {best_model_name} ...")
    final_pipe = make_supervised_models()[best_model_name]
    final_pipe.fit(x, y)
    joblib.dump(final_pipe, output_dir / "solana_bot_model.joblib")

    # [修复]: 并不是所有模型都支持 feature_importances_ 属性 (如 HistGradientBoosting)
    model_obj = final_pipe.named_steps["model"]
    if hasattr(model_obj, "feature_importances_"):
        importance = model_obj.feature_importances_
        # 确保特征名列表与重要性数组长度完全一致
        if len(cols) == len(importance):
            imp_df = pd.DataFrame({"feature": cols, "importance": importance}).sort_values("importance", ascending=False)
            save_dataframe(imp_df, output_dir / "feature_importance.csv")
            print("特征重要性评估完成并已保存。")
        else:
            print(f"警告: 特征数量({len(cols)})与重要性权重数量({len(importance)})不匹配，跳过保存重要性评估。")
    else:
        print(f"提示: 模型 {best_model_name} 不支持直接提取特征重要性，已跳过此步骤。")

    # 混淆矩阵可视化
    # [性能优化]: n_jobs=-1 开启预测的并发计算
    y_pred = cross_val_predict(final_pipe, x, y, cv=cv, n_jobs=-1)
    ConfusionMatrixDisplay.from_predictions(y, y_pred, cmap='Blues')
    plt.title(f"Confusion Matrix: {best_model_name}")
    plt.savefig(output_dir / "confusion_matrix.png")
    plt.close()

    print(f"监督学习完成。最佳模型: {best_model_name}, F1: {max_f1:.4f}")

if __name__ == "__main__":
    out = Path("output")
    # 1. 探索性聚类（对应开题报告分型研究）
    run_unsupervised_clustering(out, "features.csv", n_clusters=3)
    
    # 2. 监督学习与验证闭环
    train_supervised(out, "features_labeled.csv")
    
    # 3. 基线对比
    labeled_df = load_features(out, "features_labeled.csv")
    run_heuristic_baseline(labeled_df, out)
    labeled_df = load_features(out, "features_labeled.csv")
    run_heuristic_baseline(labeled_df, out)