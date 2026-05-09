import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.cluster import DBSCAN
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .paper_utils import FEATURE_NAME_ZH, ensure_output_dir, load_features, numeric_feature_columns, save_dataframe


def choose_k(x, min_k=2, max_k=6):
    best_k = min_k
    best_score = -1
    rows = []
    upper = min(max_k, len(x) - 1)
    for k in range(min_k, upper + 1):
        labels = KMeans(n_clusters=k, random_state=42, n_init=20).fit_predict(x)
        score = silhouette_score(x, labels) if len(set(labels)) > 1 else -1
        rows.append({"k": k, "silhouette": score})
        if score > best_score:
            best_k = k
            best_score = score
    return best_k, pd.DataFrame(rows)


def infer_cluster_type(row):
    avg_tx = row.get("avg_tx_per_day", 0)
    interval = row.get("avg_interval_seconds", 10**9)
    unique_tokens = row.get("unique_tokens", 0)
    program_entropy = row.get("program_entropy", 0)
    token_entropy = row.get("token_entropy", 0)
    new_token_ratio = row.get("new_token_interaction_ratio", 0)
    core_dex_ratio = row.get("core_dex_interaction_ratio", 0)
    priority_fee_ratio = row.get("priority_fee_nonzero_ratio", 0)
    instruction_entropy = row.get("instruction_program_entropy", 0)

    if new_token_ratio >= 0.35 and priority_fee_ratio >= 0.2:
        return "新币狙击型"
    if core_dex_ratio >= 0.5 and instruction_entropy >= 2.5:
        return "跨DEX套利型"
    if unique_tokens >= 200 and token_entropy >= 4.5:
        return "多代币扫描/狙击型"
    if avg_tx >= 2500 and interval <= 30:
        return "高频套利/做市型"
    if program_entropy <= 2.2 and unique_tokens <= 50:
        return "固定协议专用型"
    return "混合策略型"


def run_cluster_analysis(output_dir=None, feature_file="features.csv", k=None):
    output_dir = ensure_output_dir(output_dir)
    df = load_features(output_dir, feature_file)
    feature_cols = numeric_feature_columns(df)
    if len(df) < 3:
        raise ValueError("聚类至少需要3个样本。")

    preprocess = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    x = preprocess.fit_transform(df[feature_cols])

    if k is None:
        k, k_scores = choose_k(x)
    else:
        k_scores = pd.DataFrame([{"k": k, "silhouette": None}])
    save_dataframe(k_scores, output_dir / "cluster_k_scores.csv")

    model = KMeans(n_clusters=k, random_state=42, n_init=30)
    clusters = model.fit_predict(x)
    out = df.copy()
    out["cluster"] = clusters

    profile = out.groupby("cluster")[feature_cols].mean().reset_index()
    profile["count"] = out.groupby("cluster").size().values
    profile["inferred_type"] = profile.apply(infer_cluster_type, axis=1)
    save_dataframe(profile, output_dir / "cluster_profile.csv")

    type_map = profile.set_index("cluster")["inferred_type"].to_dict()
    out["inferred_type"] = out["cluster"].map(type_map)
    save_dataframe(out, output_dir / "cluster_assignments.csv")

    gmm = GaussianMixture(n_components=k, random_state=42, covariance_type="full")
    gmm_clusters = gmm.fit_predict(x)
    gmm_out = df.copy()
    gmm_out["cluster"] = gmm_clusters
    gmm_profile = gmm_out.groupby("cluster")[feature_cols].mean().reset_index()
    gmm_profile["count"] = gmm_out.groupby("cluster").size().values
    gmm_profile["inferred_type"] = gmm_profile.apply(infer_cluster_type, axis=1)
    save_dataframe(gmm_out, output_dir / "gmm_cluster_assignments.csv")
    save_dataframe(gmm_profile, output_dir / "gmm_cluster_profile.csv")

    dbscan = DBSCAN(eps=1.8, min_samples=max(3, min(10, len(df) // 10)))
    dbscan_out = df.copy()
    dbscan_out["cluster"] = dbscan.fit_predict(x)
    save_dataframe(dbscan_out, output_dir / "dbscan_cluster_assignments.csv")

    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(x)
    plot_df = pd.DataFrame(
        {
            "PC1": coords[:, 0],
            "PC2": coords[:, 1],
            "cluster": clusters.astype(str),
            "address": out["address"] if "address" in out.columns else out.index.astype(str),
        }
    )
    plt.figure(figsize=(9, 6))
    sns.scatterplot(data=plot_df, x="PC1", y="PC2", hue="cluster", s=70, palette="tab10")
    plt.title("KMeans聚类结果（PCA二维投影）")
    plt.tight_layout()
    plt.savefig(output_dir / "cluster_pca.png", dpi=200, bbox_inches="tight")
    plt.savefig(output_dir / "cluster_pca.pdf", bbox_inches="tight")
    plt.close()

    readable = profile.rename(columns={c: FEATURE_NAME_ZH.get(c, c) for c in profile.columns})
    save_dataframe(readable, output_dir / "cluster_profile_cn.csv")
    print(f"聚类分析已完成: k={k}, 输出目录={output_dir}")
    return out, profile


if __name__ == "__main__":
    run_cluster_analysis()
