from xtquant import xtdata
import pandas as pd
import numpy as np

# ===================== 1. 基础参数配置 =====================
stock_list = [
    "600519.SH",  # 贵州茅台
    "000858.SZ",  # 五粮液
    "002594.SZ",  # 比亚迪
    "601318.SH",  # 中国平安
    "300750.SZ",  # 宁德时代
    "600036.SH",  # 招商银行
    "000001.SZ",  # 平安银行
    "601899.SH"   # 紫金矿业
]
start_time = "20240101"
end_time = "20260531"

table_list = ['Balance','Income']

# 下载行情、财务数据
xtdata.download_history_data2(
    stock_list=stock_list,
    period="1d",
    start_time=start_time,
    end_time=end_time
)
xtdata.download_financial_data(stock_list=stock_list, table_list=table_list)

# ===================== 2. 读取日线行情 =====================
data_dict = xtdata.get_market_data_ex(
    field_list=["close"],
    stock_list=stock_list,
    period="1d",
    start_time=start_time,
    end_time=end_time,
    count=-1,
    dividend_type="front"
)

all_price_data = []
for code, df_raw in data_dict.items():
    df = df_raw.reset_index()
    df.columns = ["date_str", "price"]
    df["symbol"] = code
    df["date"] = pd.to_datetime(df["date_str"], format="%Y%m%d")
    all_price_data.append(df[["date", "symbol", "price"]])

price_df = pd.concat(all_price_data, ignore_index=True)
print("✅ 行情数据读取完成")

# ===================== 3. 财务数据获取 + 官方接口获取总股本 =====================
def get_stock_finance(stock_code):
    # 新版标准接口获取股票基础信息，提取总股本 TotalVolume
    instrument_info = xtdata.get_instrument_detail(stock_code)
    total_share = instrument_info["TotalVolume"]

    # 获取资产负债表、利润表
    fin_res = xtdata.get_financial_data(
        stock_list=[stock_code],
        table_list=table_list,
        start_time=start_time,
        end_time=end_time
    )

    # 利润表（已验证可用字段）
    df_income = fin_res[stock_code]["Income"].reset_index()
    df_income.rename(columns={"m_timetag":"end_date"}, inplace=True)
    df_income["end_date"] = pd.to_datetime(df_income["end_date"], format="%Y%m%d")
    df_income = df_income[["end_date", "operating_revenue", "net_profit_excl_min_int_inc", "s_fa_eps_basic"]]
    df_income.columns = ["end_date", "sales", "profit", "eps"]

    # 资产负债表（已验证可用字段）
    df_balance = fin_res[stock_code]["Balance"].reset_index()
    df_balance.rename(columns={"m_timetag":"end_date"}, inplace=True)
    df_balance["end_date"] = pd.to_datetime(df_balance["end_date"], format="%Y%m%d")
    df_balance = df_balance[["end_date", "cash_equivalents", "tot_liab", "tot_shrhldr_eqy_excl_min_int"]]
    df_balance.columns = ["end_date", "cash", "debt", "total_equity"]

    # 合并财务报表
    fin_merge = pd.merge(df_income, df_balance, on="end_date", how="outer")
    # 填充总股本（静态最新值）
    fin_merge["total_share"] = total_share
    # 每股净资产 = 归属母公司权益 / 总股本
    fin_merge["book_value"] = fin_merge["total_equity"] / fin_merge["total_share"]

    return fin_merge[["end_date", "eps", "book_value", "sales", "total_share", "profit", "cash", "debt"]]

# ===================== 4. 行情财务时间对齐拼接 =====================
total_stock_list = []
for code in stock_list:
    single_price = price_df[price_df["symbol"] == code].copy().sort_values("date")
    try:
        single_fin = get_stock_finance(code).sort_values("end_date")
    except Exception as e:
        print(f"⚠️ {code} 财务数据获取失败: {e}")
        continue

    merge_df = pd.merge_asof(
        single_price,
        single_fin,
        left_on="date",
        right_on="end_date",
        direction="backward"
    )

    # 计算因子所需衍生字段
    merge_df["market_cap"] = merge_df["price"] * merge_df["total_share"]
    merge_df["dividend"] = merge_df["profit"] * 0.3 / merge_df["total_share"]
    merge_df["ebitda"] = merge_df["profit"] * 1.2

    keep_cols = [
        "date", "symbol", "price", "eps", "book_value", "sales",
        "dividend", "market_cap", "debt", "cash", "ebitda"
    ]
    
    merge_df = merge_df[keep_cols].dropna()
    if not merge_df.empty:
        total_stock_list.append(merge_df)

# 导出数据集
if total_stock_list:
    final_df = pd.concat(total_stock_list, ignore_index=True)
    final_df.to_csv("qmt_multi_stock.csv", index=False, encoding="utf-8-sig")
    print("✅ 多股票行情+财务数据保存成功:qmt_multi_stock.csv")
    print(final_df.head())
else:
    print("❌ 无有效财务数据,请检查时间区间或QMT权限")