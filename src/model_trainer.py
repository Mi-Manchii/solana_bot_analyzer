import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import ConfusionMatrixDisplay, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .paper_utils import ensure_output_dir, load_features, numeric_feature_columns, save_dataframe


FEATURE_GROUPS = {
    "activity": ["total_transactions", "unique_days", "avg_tx_per_day", "max_tx_in_day"],
    "time": [
        "night_ratio",
        "weekend_ratio",
        "avg_interval_seconds",
        "median_interval_seconds",
        "std_interval_seconds",
        "cv_interval",
        "hourly_entropy",
        "daily_cv",
        "max_inactive_days",
    ],
    "interaction": ["unique_programs", "program_entropy", "unique_tokens", "token_entropy"],
    "solana_specific": [
        "avg_priority_fee_lamports",
        "priority_fee_cv",
        "priority_fee_nonzero_ratio",
        "avg_compute_units",
        "avg_instruction_count",
        "instruction_program_entropy",
        "instruction_type_entropy",
        "core_dex_interaction_ratio",
        "pump_fun_interaction_ratio",
        "new_token_interaction_ratio",
    ],
}


def make_models():
    models = {
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=400,
                        min_samples_leaf=2,
                        class_weight="balanced",
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, random_state=42)),
            ]
        ),
    }
    try:
        from xgboost import XGBClassifier

        models["xgboost"] = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("model", XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42)),
            ]
        )
    except ImportError:
        pass
    try:
        from lightgbm import LGBMClassifier

        models["lightgbm"] = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("model", LGBMClassifier(n_estimators=300, learning_rate=0.05, random_state=42)),
            ]
        )
    except ImportError:
        pass
    return models


def choose_cv(y, requested=5):
    min_class_count = int(y.value_counts().min())
    if min_class_count < 2:
        raise ValueError("监督学习至少需要每一类各2个样本。请补充普通用户负样本。")
    return StratifiedKFold(n_splits=max(2, min(requested, min_class_count)), shuffle=True, random_state=42)


def evaluate(feature_df, feature_cols, output_dir, cv):
    x = feature_df[feature_cols]
    y = pd.to_numeric(feature_df["label"], errors="raise").astype(int)
    rows = []
    best_name = None
    best_f1 = -1

    for name, model in make_models().items():
        scores = cross_validate(
            model,
            x,
            y,
            cv=cv,
            scoring=["accuracy", "precision", "recall", "f1", "roc_auc"],
            error_score="raise",
        )
        row = {"model": name}
        for key, values in scores.items():
            if key.startswith("test_"):
                metric = key.replace("test_", "")
                row[f"{metric}_mean"] = float(values.mean())
                row[f"{metric}_std"] = float(values.std())
        rows.append(row)
        if row["f1_mean"] > best_f1:
            best_f1 = row["f1_mean"]
            best_name = name

    metrics = pd.DataFrame(rows).sort_values("f1_mean", ascending=False)
    save_dataframe(metrics, output_dir / "model_cv_metrics.csv")
    return best_name, metrics


def run_ablation(feature_df, feature_cols, output_dir, cv):
    x = feature_df[feature_cols]
    y = pd.to_numeric(feature_df["label"], errors="raise").astype(int)
    rows = []
    tests = {"all_features": feature_cols}
    for group, cols in FEATURE_GROUPS.items():
        remaining = [c for c in feature_cols if c not in cols]
        if 0 < len(remaining) < len(feature_cols):
            tests[f"without_{group}"] = remaining

    for setting, cols in tests.items():
        model = make_models()["random_forest"]
        scores = cross_validate(model, x[cols], y, cv=cv, scoring=["accuracy", "precision", "recall", "f1"])
        row = {"setting": setting, "num_features": len(cols)}
        for key, values in scores.items():
            if key.startswith("test_"):
                row[key.replace("test_", "")] = float(values.mean())
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("f1", ascending=False)
    save_dataframe(out, output_dir / "ablation_metrics.csv")
    return out


def train_supervised(output_dir=None, feature_file="features_labeled.csv", cv_folds=5):
    output_dir = ensure_output_dir(output_dir)
    feature_path = output_dir / feature_file
    if not feature_path.exists():
        print(f"未找到 {feature_path}，跳过监督学习。")
        print("请准备 output/features_labeled.csv，其中 label=1 为疑似机器人，label=0 为普通用户。")
        return None

    df = load_features(output_dir, feature_file)
    if "label" not in df.columns:
        raise ValueError("features_labeled.csv 必须包含 label 列。")
    y = pd.to_numeric(df["label"], errors="raise").astype(int)
    if y.nunique() < 2:
        raise ValueError("监督学习需要同时包含 label=1 和 label=0。")

    feature_cols = numeric_feature_columns(df)
    cv = choose_cv(y, cv_folds)
    best_name, metrics = evaluate(df, feature_cols, output_dir, cv)
    run_ablation(df, feature_cols, output_dir, cv)

    x = df[feature_cols]
    y_pred = cross_val_predict(make_models()[best_name], x, y, cv=cv)
    report = classification_report(y, y_pred, output_dict=True, zero_division=0)
    with (output_dir / "classification_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    ConfusionMatrixDisplay.from_predictions(y, y_pred, values_format="d")
    plt.title(f"Cross-validated Confusion Matrix: {best_name}")
    plt.tight_layout()
    plt.savefig(output_dir / "confusion_matrix.png", dpi=200, bbox_inches="tight")
    plt.close()

    final_model = make_models()[best_name]
    final_model.fit(x, y)
    joblib.dump({"model": final_model, "features": feature_cols}, output_dir / "best_model.joblib")

    estimator = final_model.named_steps["model"]
    if hasattr(estimator, "feature_importances_"):
        importance = pd.DataFrame({"feature": feature_cols, "importance": estimator.feature_importances_})
        importance = importance.sort_values("importance", ascending=False)
        save_dataframe(importance, output_dir / "feature_importance.csv")
        plt.figure(figsize=(8, max(4, len(importance) * 0.28)))
        sns.barplot(data=importance.head(25), x="importance", y="feature", color="steelblue")
        plt.title("Feature Importance")
        plt.tight_layout()
        plt.savefig(output_dir / "feature_importance.png", dpi=200, bbox_inches="tight")
        plt.close()

    print("监督学习已完成。")
    print(metrics.to_string(index=False))
    return metrics


if __name__ == "__main__":
    train_supervised()
