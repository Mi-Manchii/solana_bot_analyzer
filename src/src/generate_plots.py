# generate_plots.py
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# 设置中文字体（确保系统有中文字体，如 SimHei, Microsoft YaHei 等）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

def plot_distributions(output_dir=None):
    """读取 features.csv 并生成多个分布图（中文版）"""
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    feat_path = output_dir / 'features.csv'
    if not feat_path.exists():
        print(f"错误：未找到 {feat_path}，请先运行 main.py 生成特征文件。")
        return

    df = pd.read_csv(feat_path)

    # 设置绘图风格
    sns.set(style="whitegrid", font='SimHei')  # 指定 seaborn 字体

    # 原有9个特征的中文标签
    plot_configs = [
        ('avg_tx_per_day', '日均交易数'),
        ('max_tx_in_day', '单日最大交易数'),
        ('night_ratio', '夜间交易比例 (0-5点)'),
        ('weekend_ratio', '周末交易比例'),
        ('avg_interval_seconds', '平均交易间隔 (秒)'),
        ('cv_interval', '交易间隔变异系数'),
        ('hourly_entropy', '小时交易熵'),
        ('daily_cv', '每日交易数变异系数'),
        ('feb_2026_tx_count', '2026年2月交易数'),
    ]

    # 第一组图：3x3 布局，增大图片尺寸和字体
    fig, axes = plt.subplots(3, 3, figsize=(18, 14))
    axes = axes.flatten()
    for ax, (col, label) in zip(axes, plot_configs):
        sns.histplot(df[col], bins=30, kde=True, ax=ax, color='steelblue')
        ax.set_title(f'{label} 分布', fontsize=14, fontweight='bold')
        ax.set_xlabel(label, fontsize=12)
        ax.set_ylabel('频次', fontsize=12)
        ax.tick_params(labelsize=10)
        # 添加网格线（透明度）
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'feature_distributions.png', dpi=200, bbox_inches='tight')
    plt.savefig(output_dir / 'feature_distributions.pdf', bbox_inches='tight')
    print(f"分布图已保存至 {output_dir / 'feature_distributions.png'} 和 .pdf")

    # 第二组图：新增的4个多样性特征（如果存在）
    new_features = [
        ('unique_programs', '调用程序种类数'),
        ('program_entropy', '程序调用熵'),
        ('unique_tokens', '交互代币种类数'),
        ('token_entropy', '代币交互熵')
    ]
    existing = [(col, label) for col, label in new_features if col in df.columns]
    if existing:
        n = len(existing)
        if n == 4:
            fig2, axes2 = plt.subplots(2, 2, figsize=(14, 10))
            axes2 = axes2.flatten()
        else:
            fig2, axes2 = plt.subplots(1, n, figsize=(6*n, 5))
            if n == 1:
                axes2 = [axes2]
        for ax, (col, label) in zip(axes2, existing):
            sns.histplot(df[col], bins=30, kde=True, ax=ax, color='darkorange')
            ax.set_title(f'{label} 分布', fontsize=14, fontweight='bold')
            ax.set_xlabel(label, fontsize=12)
            ax.set_ylabel('频次', fontsize=12)
            ax.tick_params(labelsize=10)
            ax.grid(True, alpha=0.3)
        # 隐藏多余的子图（如果有）
        for ax in axes2[len(existing):]:
            ax.set_visible(False)
        plt.tight_layout()
        plt.savefig(output_dir / 'new_feature_distributions.png', dpi=200, bbox_inches='tight')
        plt.savefig(output_dir / 'new_feature_distributions.pdf', bbox_inches='tight')
        print(f"新特征分布图已保存至 {output_dir / 'new_feature_distributions.png'} 和 .pdf")
    else:
        print("未找到新增的多样性特征列，跳过第二组图。")

    # 相关性热力图（中文化）
    plt.figure(figsize=(16, 14))
    numeric_cols = df.select_dtypes(include=['number']).columns
    corr = df[numeric_cols].corr()

    # 生成中文标签映射（将列名翻译为中文）
    label_map = {
        'total_transactions': '总交易数',
        'unique_days': '活跃天数',
        'avg_tx_per_day': '日均交易数',
        'max_tx_in_day': '单日最大交易数',
        'night_ratio': '夜间比例',
        'weekend_ratio': '周末比例',
        'avg_interval_seconds': '平均间隔(秒)',
        'median_interval_seconds': '中位间隔(秒)',
        'std_interval_seconds': '间隔标准差',
        'cv_interval': '间隔变异系数',
        'hourly_entropy': '小时熵',
        'peak_hour': '最活跃小时',
        'daily_cv': '每日交易CV',
        'max_inactive_days': '最长无交易天数',
        'recent_tx_ratio_7d': '近7天交易比例',
        'feb_2026_tx_count': '2月交易数',
        'feb_2026_active_days': '2月活跃天数',
        'unique_programs': '程序种类',
        'program_entropy': '程序熵',
        'unique_tokens': '代币种类',
        'token_entropy': '代币熵',
    }
    # 只保留存在的列
    corr = corr.loc[[c for c in corr.index if c in label_map], [c for c in corr.columns if c in label_map]]
    corr.index = [label_map.get(c, c) for c in corr.index]
    corr.columns = [label_map.get(c, c) for c in corr.columns]

    sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', linewidths=0.5,
                annot_kws={'size': 10}, cbar_kws={'shrink': 0.8})
    plt.title('特征相关性矩阵', fontsize=18, fontweight='bold', pad=20)
    plt.xticks(fontsize=11, rotation=45, ha='right')
    plt.yticks(fontsize=11)
    plt.tight_layout()
    plt.savefig(output_dir / 'feature_correlation.png', dpi=200, bbox_inches='tight')
    plt.savefig(output_dir / 'feature_correlation.pdf', bbox_inches='tight')
    print(f"相关性热力图已保存至 {output_dir / 'feature_correlation.png'} 和 .pdf")

if __name__ == "__main__":
    plot_distributions()