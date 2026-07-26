import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
import pandas as pd
import numpy as np
import time

# 1. 选定一批A股标的（先少选几只测试，降低请求压力）
stock_list = [
    "600519", "000858"
]
start_date = "20240101"
end_date = "20241231"

total_data = []

for symbol in stock_list:
    try:
        print(f"正在拉取股票{symbol}数据")
        # 每次请求前休眠2秒，防止接口频繁访问被断开
        time.sleep(2)
        # 日线行情
        df_price = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="hfq"  # 前复权，消除除权除息影响
        )
        df_price["date"] = pd.to_datetime(df_price["date"])
        df_price = df_price[["date", "收盘"]].rename(columns={"收盘": "price"})
        df_price["symbol"] = symbol

        # 季度财务数据
        df_fin = ak.stock_financial_analysis_indicator(symbol=symbol)
        df_fin["报告期"] = pd.to_datetime(df_fin["报告期"])
        # 关键财务指标
        df_fin = df_fin[["报告期", "基本每股收益(元)", "每股净资产(元)", "营业总收入", "总股本", "归属母公司净利润"]]
        df_fin.columns = ["end_date", "eps", "book_value", "sales", "total_share", "profit"]

        # 前向填充财务数据到每日行情
        df_merge = pd.merge_asof(
            df_price.sort_values("date"),
            df_fin.sort_values("end_date"),
            left_on="date",
            right_on="end_date",
            direction="backward"
        )

        # 计算衍生财务字段
        df_merge["market_cap"] = df_merge["price"] * df_merge["total_share"]
        df_merge["debt"] = df_merge["market_cap"] * 0.3
        df_merge["cash"] = df_merge["market_cap"] * 0.15
        df_merge["dividend"] = df_merge["profit"] * 0.3 / df_merge["total_share"]
        df_merge["ebitda"] = df_merge["profit"] * 1.2

        keep_cols = ["date", "symbol", "price", "eps", "book_value", "sales",
                     "dividend", "market_cap", "debt", "cash", "ebitda"]
        df_merge = df_merge[keep_cols].dropna()
        if not df_merge.empty:
            total_data.append(df_merge)
            print(f"{symbol} 数据拉取成功，有效行数：{len(df_merge)}")

    except Exception as e:
        print(f"{symbol}拉取失败：{e}")
        continue

# 容错：判断是否有成功拉取的数据
if len(total_data) == 0:
    raise Exception("所有股票数据均拉取失败，请检查网络或减少股票数量、拉长请求间隔重试！")

# 合并所有股票数据
df_all = pd.concat(total_data, ignore_index=True)
df_all.to_csv("a_multi_stock.csv", index=False, encoding="utf-8-sig")
print(f"多股票A股数据保存完成,总样本行数:{len(df_all)}")