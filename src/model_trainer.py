# src/model_trainer.py
import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

# 设置中文字体，防止论文图表乱码 (根据系统可能需要调整，这里给出通用设定)
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS'] 
plt.rcParams['axes.unicode_minus'] = False

def train_and_evaluate():
    output_dir = Path(__file__).parent.parent / "output"
    data_path = output_dir / "heuristic_scores_final.csv"
    map_path = output_dir / "bot_label_mapping.json"
    
    if not data_path.exists():
        print("❌ 找不到标注数据，请先运行 src/heuristic_baseline.py")
        return

    print("🚀 开始加载数据并训练机器学习分类模型...")
    df = pd.read_csv(data_path)
    
    with open(map_path, "r", encoding="utf-8") as f:
        bot_map = json.load(f)

    # 1. 特征清洗：去除无关列和由于一票否决导致的推导列
    drop_cols = ['address', 'heuristic_is_bot', 'heuristic_score', 'bot_type_id', 'bot_type_name']
    # 移除所有 rule_ 开头的规则列，让模型自己去学底层特征
    drop_cols += [c for c in df.columns if c.startswith('rule_')]
    
    X = df.drop(columns=[c for c in drop_cols if c in df.columns]).fillna(0)
    y = df['bot_type_id']

    # 如果样本太少（比如目前只有7个），跳过训练保护
    if len(df) < 15:
        print(f"⚠️ 当前总样本仅 {len(df)} 个，不足以进行完整的机器学习训练与交叉验证。")
        print("💡 请先通过 address_pool.txt 抓取至少 50-100 个地址的数据！")
        return

    # 2. 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

    # 3. 训练随机森林模型
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    rf_model.fit(X_train, y_train)
    
    # 4. 模型评估
    y_pred = rf_model.predict(X_test)
    print("\n📊 === 模型分类报告 (Classification Report) ===")
    
    # 将 ID 映射回中文名
    target_names = [bot_map.get(str(cls_id), f"类型 {cls_id}") for cls_id in np.unique(y_test)]
    print(classification_report(y_test, y_pred, target_names=target_names, zero_division=0))

    # 5. 绘制混淆矩阵 (Confusion Matrix) -> 论文必备图表 1
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                xticklabels=target_names, yticklabels=target_names)
    plt.title('Solana Bot 多模态分类混淆矩阵')
    plt.ylabel('真实标签 (True Label)')
    plt.xlabel('预测标签 (Predicted Label)')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    cm_path = output_dir / "confusion_matrix.png"
    plt.savefig(cm_path, dpi=300)
    print(f"🖼️ 已生成混淆矩阵图表: {cm_path}")

    # 6. 提取并绘制特征重要性 (Feature Importance) -> 论文必备图表 2
    importances = rf_model.feature_importances_
    feat_df = pd.DataFrame({
        'Feature': X.columns,
        'Importance': importances
    }).sort_values(by='Importance', ascending=False).head(15) # 取前15个最重要的特征
    
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Importance', y='Feature', data=feat_df, palette='viridis')
    plt.title('识别 Solana 机器人的 Top 15 核心特征重要性 (RF)')
    plt.tight_layout()
    feat_path = output_dir / "feature_importance.png"
    plt.savefig(feat_path, dpi=300)
    print(f"🖼️ 已生成特征重要性图表: {feat_path}")

    # 保存模型
    model_path = output_dir / "solana_bot_rf_model.joblib"
    joblib.dump(rf_model, model_path)
    print(f"💾 模型已保存至: {model_path}")

if __name__ == "__main__":
    train_and_evaluate()