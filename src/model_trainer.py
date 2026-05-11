import pandas as pd
import numpy as np
import json
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

def train_and_evaluate():
    output_dir = Path(__file__).parent.parent / "output"
    data_path = output_dir / "heuristic_scores_final.csv"
    
    df = pd.read_csv(data_path)
    with open(output_dir / "bot_label_mapping.json", "r", encoding="utf-8") as f:
        bot_map = json.load(f)

    # 1. 特征清洗与准备
    drop_cols = ['address', 'heuristic_is_bot', 'heuristic_score', 'bot_type_id', 'bot_type_name']
    drop_cols += [c for c in df.columns if c.startswith('rule_')]
    
    X_raw = df.drop(columns=[c for c in drop_cols if c in df.columns]).fillna(0)
    y = df['bot_type_id']

    # ---------- 修复：特征标准化 ----------
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)
    X = pd.DataFrame(X_scaled, columns=X_raw.columns)

    if len(df) < 15: return

    # 2. 划分与训练
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
    rf_model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight='balanced')
    rf_model.fit(X_train, y_train)
    
    # 3. 评估与可视化 (混淆矩阵与特征重要性)
    y_pred = rf_model.predict(X_test)
    target_names = [bot_map.get(str(int(cls_id)), f"Type {cls_id}") for cls_id in np.unique(y)]
    print(classification_report(y_test, y_pred, target_names=target_names))

    # 特征重要性绘图 [cite: 107, 214]
    importances = rf_model.feature_importances_
    feat_df = pd.DataFrame({'Feature': X_raw.columns, 'Importance': importances}).sort_values(by='Importance', ascending=False).head(15)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(x='Importance', y='Feature', data=feat_df)
    plt.title('Solana Bot Detection - Feature Importance')
    plt.tight_layout()
    plt.savefig(output_dir / "feature_importance.png")
    
    joblib.dump(rf_model, output_dir / "solana_bot_rf_model.joblib")