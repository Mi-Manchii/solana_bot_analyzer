from pathlib import Path

from src.case_exporter import export_cases
from src.cluster_analyzer import run_cluster_analysis
from src.heuristic_baseline import run_heuristic_baseline
from src.model_trainer import train_supervised


def main():
    project_dir = Path(__file__).parent
    output_dir = project_dir / "output"

    print("1/4 运行启发式规则 baseline...")
    run_heuristic_baseline(output_dir)

    print("2/4 运行无监督聚类与行为分型...")
    run_cluster_analysis(output_dir)

    print("3/4 导出典型案例候选...")
    export_cases(output_dir, top_n=10)

    print("4/4 尝试运行监督学习模型...")
    train_supervised(output_dir)

    print("论文实验输出完成。请查看 output/ 目录。")


if __name__ == "__main__":
    main()
