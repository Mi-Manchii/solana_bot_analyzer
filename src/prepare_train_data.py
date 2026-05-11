# prepare_train_data.py
import pandas as pd

# 读取刚才启发式跑出来的评分文件
df = pd.read_csv("output/heuristic_scores_v4_scientific.csv")

# 把推断出来的 bot_type_id 复制一份，命名为 label (模型认准这个列名)
df["label"] = df["bot_type_id"]

# 另存为模型训练指定的输入文件
df.to_csv("output/features_labeled.csv", index=False)
print("✅ 训练数据集 features_labeled.csv 准备完毕！")