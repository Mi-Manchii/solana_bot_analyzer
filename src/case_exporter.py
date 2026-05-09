import pandas as pd

from .paper_utils import FEATURE_NAME_ZH, ensure_output_dir, load_features, save_dataframe


CASE_COLUMNS = [
    "address",
    "heuristic_score",
    "heuristic_confidence",
    "cluster",
    "inferred_type",
    "avg_tx_per_day",
    "max_tx_in_day",
    "avg_interval_seconds",
    "hourly_entropy",
    "unique_programs",
    "program_entropy",
    "unique_tokens",
    "token_entropy",
    "avg_priority_fee_lamports",
    "priority_fee_cv",
    "priority_fee_nonzero_ratio",
    "avg_instruction_count",
    "instruction_program_entropy",
    "core_dex_interaction_ratio",
    "pump_fun_interaction_ratio",
    "new_token_interaction_ratio",
    "night_ratio",
    "weekend_ratio",
]


def export_cases(output_dir=None, top_n=10):
    output_dir = ensure_output_dir(output_dir)
    candidates = []
    for filename in ["cluster_assignments.csv", "heuristic_scores.csv", "features.csv"]:
        path = output_dir / filename
        if path.exists():
            candidates.append(pd.read_csv(path))

    if not candidates:
        raise FileNotFoundError("未找到可用于案例分析的输出文件。")

    df = candidates[0]
    for other in candidates[1:]:
        if "address" in df.columns and "address" in other.columns:
            add_cols = [c for c in other.columns if c not in df.columns or c == "address"]
            df = df.merge(other[add_cols], on="address", how="left")

    if "heuristic_score" in df.columns:
        df = df.sort_values(["heuristic_score", "avg_tx_per_day"], ascending=False)
    elif "avg_tx_per_day" in df.columns:
        df = df.sort_values("avg_tx_per_day", ascending=False)

    existing = [c for c in CASE_COLUMNS if c in df.columns]
    cases = df[existing].head(top_n).copy()
    save_dataframe(cases, output_dir / "case_candidates.csv")

    cn = cases.rename(columns={c: FEATURE_NAME_ZH.get(c, c) for c in cases.columns})
    save_dataframe(cn, output_dir / "case_candidates_cn.csv")
    print(f"典型案例候选已导出: {output_dir / 'case_candidates_cn.csv'}")
    return cases


if __name__ == "__main__":
    export_cases()
