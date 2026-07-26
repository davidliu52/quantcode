import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow.keras.layers import Dense, Dropout

# 1. 加载数据
data = pd.read_csv("qmt_multi_stock.csv", parse_dates=["date"])
data = data.dropna()

# 2. 构造因子：sales全0，去掉PS因子，只用4个因子
def calc_factors(df):
    fac = pd.DataFrame()
    fac["PE"] = df["price"] / df["eps"]
    fac["PB"] = df["price"] / df["book_value"]
    fac["DY"] = df["dividend"] / df["price"]
    fac["EV_EBITDA"] = (df["market_cap"] + df["debt"] - df["cash"]) / df["ebitda"]
    return fac

factors = calc_factors(data)
data = pd.concat([data.reset_index(drop=True), factors.reset_index(drop=True)], axis=1)

# 3. 构造未来收益率标签
data["future_ret"] = data.groupby("symbol")["price"].pct_change().shift(-1)
factor_cols = ["PE", "PB", "DY", "EV_EBITDA"]
data = data.dropna(subset=factor_cols + ["future_ret"])

# 4. 横截面标准化
def cross_section_norm(df_day):
    scaler = StandardScaler()
    df_day[factor_cols] = scaler.fit_transform(df_day[factor_cols])
    return df_day

data_norm = data.groupby("date").apply(cross_section_norm).reset_index(drop=True)

# 5. 时序划分训练测试集
split_date = data_norm["date"].quantile(0.7)
train_df = data_norm[data_norm["date"] < split_date]
test_df = data_norm[data_norm["date"] >= split_date]

X_train = train_df[factor_cols].values
y_train = train_df["future_ret"].values
X_test = test_df[factor_cols].values
y_test = test_df["future_ret"].values

# 6. 搭建DNN模型（输入改为4维特征）
model = tf.keras.Sequential([
    Dense(64, activation="relu", input_shape=(4,)),
    Dropout(0.2),
    Dense(32, activation="relu"),
    Dense(1)
])
model.compile(optimizer="adam", loss="mse", metrics=["mae"])
history = model.fit(
    X_train, y_train,
    epochs=40,
    batch_size=32,
    validation_data=(X_test, y_test),
    verbose=1
)

import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

class AStockCrossBacktest:
    def __init__(self, model, test_data, top_n=3, init_cap=100000):
        self.model = model
        self.df = test_data.copy()
        self.top_n = top_n
        self.init_cap = init_cap
        self.cash = init_cap
        self.hold_pos = {}
        self.nav_list = [init_cap]
        self.factor_cols = ["PE", "PB", "DY", "EV_EBITDA"]

    def run_backtest(self):
        self.df["month"] = self.df["date"].dt.to_period("M")
        month_groups = self.df.groupby("month")
        for month, group in month_groups:
            feat = group[self.factor_cols].values
            group["pred_ret"] = self.model.predict(feat, verbose=0).flatten()
            top_stocks = group.sort_values("pred_ret", ascending=False).head(self.top_n)["symbol"].unique()

            # 清仓
            for code in list(self.hold_pos.keys()):
                price = group[group["symbol"] == code]["price"].iloc[0]
                self.cash += self.hold_pos[code] * price
            self.hold_pos.clear()

            # 等权买入
            each_cap = self.cash / self.top_n
            for code in top_stocks:
                buy_price = group[group["symbol"] == code]["price"].iloc[0]
                share = each_cap / buy_price
                self.hold_pos[code] = share

            # 计算净值
            total_asset = self.cash
            for code, share in self.hold_pos.items():
                p = group[group["symbol"] == code]["price"].iloc[0]
                total_asset += share * p
            self.nav_list.append(total_asset)
        return self.nav_list

bt = AStockCrossBacktest(model, test_df, top_n=3, init_cap=100000)
nav_curve = bt.run_backtest()

# 绘图
plt.figure(figsize=(10,5))
plt.plot(nav_curve, label="A股横截面DNN多因子策略净值")
plt.title("A股多股票横截面价值因子选股净值曲线")
plt.xlabel("月度调仓次数")
plt.ylabel("账户净值（元）")
plt.legend()
plt.grid(alpha=0.3)
plt.show()