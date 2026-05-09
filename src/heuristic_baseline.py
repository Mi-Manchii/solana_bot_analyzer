import numpy as np
import pandas as pd

from .paper_utils import ensure_output_dir, load_features, save_dataframe


def _series(df, col, default=0):
    if col not in df.columns:
        return pd.Series(default, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def score_addresses(df):
    scored = df.copy()
    score = np.zeros(len(scored), dtype=float)

    rules = {
        "rule_high_frequency": _series(scored, "avg_tx_per_day") >= 257,
        "rule_large_7d_window": _series(scored, "total_transactions") >= 1800,
        "rule_short_interval": (_series(scored, "avg_interval_seconds", default=10**9) > 0)
        & (_series(scored, "avg_interval_seconds", default=10**9) <= 60),
        "rule_around_clock": _series(scored, "hourly_entropy") >= 3.5,
        "rule_program_focus": _series(scored, "program_entropy") <= 2.8,
        "rule_many_tokens": _series(scored, "unique_tokens") >= 50,
        "rule_low_rest": _series(scored, "max_inactive_days") <= 1,
        "rule_priority_fee": _series(scored, "priority_fee_nonzero_ratio") >= 0.2,
        "rule_core_dex_focus": _series(scored, "core_dex_interaction_ratio") >= 0.4,
        "rule_new_token_focus": _series(scored, "new_token_interaction_ratio") >= 0.25,
    }

    weights = {
        "rule_high_frequency": 2.0,
        "rule_large_7d_window": 1.5,
        "rule_short_interval": 1.5,
        "rule_around_clock": 1.0,
        "rule_program_focus": 1.0,
        "rule_many_tokens": 1.0,
        "rule_low_rest": 1.0,
        "rule_priority_fee": 1.0,
        "rule_core_dex_focus": 1.0,
        "rule_new_token_focus": 1.0,
    }

    for name, mask in rules.items():
        scored[name] = mask.astype(int)
        score += scored[name].to_numpy() * weights[name]

    scored["heuristic_score"] = score
    scored["heuristic_is_bot"] = (score >= 4.0).astype(int)
    scored["heuristic_confidence"] = pd.cut(
        score,
        bins=[-0.1, 2.5, 5.5, 12],
        labels=["low", "medium", "high"],
    ).astype(str)
    return scored


def run_heuristic_baseline(output_dir=None, feature_file="features.csv"):
    output_dir = ensure_output_dir(output_dir)
    df = load_features(output_dir, feature_file)
    scored = score_addresses(df)
    out_path = save_dataframe(scored, output_dir / "heuristic_scores.csv")

    summary = scored[["heuristic_score", "heuristic_is_bot"]].describe().reset_index()
    save_dataframe(summary, output_dir / "heuristic_summary.csv")
    print(f"启发式规则评分已生成: {out_path}")
    return scored


if __name__ == "__main__":
    run_heuristic_baseline()
