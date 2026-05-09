from pathlib import Path

import pandas as pd


ID_COLUMNS = {
    "address",
    "source_label",
    "source_link",
    "first_seen",
    "last_seen",
    "window_start",
    "window_end",
    "label",
    "label_name",
    "source",
    "notes",
    "bot_type",
}


FEATURE_NAME_ZH = {
    "total_transactions": "总交易数",
    "unique_days": "活跃天数",
    "avg_tx_per_day": "日均交易数",
    "max_tx_in_day": "单日最大交易数",
    "night_ratio": "夜间交易比例",
    "weekend_ratio": "周末交易比例",
    "avg_interval_seconds": "平均交易间隔",
    "median_interval_seconds": "中位交易间隔",
    "std_interval_seconds": "交易间隔标准差",
    "cv_interval": "交易间隔变异系数",
    "hourly_entropy": "小时交易熵",
    "peak_hour": "最活跃小时",
    "daily_cv": "每日交易数变异系数",
    "max_inactive_days": "最长无交易天数",
    "recent_tx_ratio_7d": "近7天交易比例",
    "feb_2026_tx_count": "2026年2月交易数",
    "feb_2026_active_days": "2026年2月活跃天数",
    "unique_programs": "调用程序种类数",
    "program_entropy": "程序调用熵",
    "unique_tokens": "交互代币种类数",
    "token_entropy": "代币交互熵",
    "avg_priority_fee_lamports": "平均优先费用",
    "priority_fee_cv": "优先费用变异系数",
    "priority_fee_nonzero_ratio": "优先费用非零比例",
    "avg_fee_lamports": "平均交易费用",
    "avg_compute_units": "平均计算单元",
    "avg_instruction_count": "平均指令数",
    "instruction_program_entropy": "指令程序熵",
    "instruction_type_entropy": "指令类型熵",
    "core_dex_interaction_ratio": "核心DEX交互占比",
    "pump_fun_interaction_ratio": "Pump.fun交互占比",
    "new_token_interaction_ratio": "新代币交互比例",
    "tx_count_7d": "7天窗口交易数",
    "total_tx_available": "可获取交易数",
}


def ensure_output_dir(output_dir=None):
    path = Path(output_dir) if output_dir else Path.cwd() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_features(output_dir=None, filename="features.csv"):
    output_dir = ensure_output_dir(output_dir)
    path = output_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"未找到特征文件: {path}")
    return pd.read_csv(path)


def numeric_feature_columns(df):
    cols = []
    for col in df.columns:
        if col in ID_COLUMNS:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            # 只有当列中至少有一个非空值时才将其作为特征，避免被 Imputer 剔除导致长度不匹配
            if df[col].notna().sum() > 0:
                cols.append(col)
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0:
            df[col] = converted
            cols.append(col)
    return cols


def save_dataframe(df, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
