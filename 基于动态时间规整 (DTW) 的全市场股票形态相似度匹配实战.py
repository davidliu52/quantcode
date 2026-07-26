import akshare as ak
import pandas as pd
import numpy as np
from dtaidistance import dtw
from tqdm import tqdm
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

# 解决中文乱码问题
plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows系统
# plt.rcParams['font.sans-serif'] = ['STHeiti']  # MacOS系统
plt.rcParams['axes.unicode_minus'] = False

# -------------------------- 配置参数 --------------------------
TARGET_SYMBOL = "600519"  # 目标股票代码(示例：贵州茅台)
LOOKBACK_DAYS = 30        # 形态分析周期(单位：交易日)
PREDICT_DAYS = 5          # 计算后续N日收益
SIMILAR_NUM = 10          # 展示最相似的股票数量
START_DATE = "20250102"   # 数据起始日期(确保覆盖足够历史)
# ----------------------------------------------------------------

def get_stock_data(symbol: str) -> pd.DataFrame:
    """获取股票日线数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", 
                                start_date=START_DATE, adjust="hfq")
        if df.empty:
            return None
        df.set_index("日期", inplace=True)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as e:
        return None

def plot_similar_stocks(target_series: np.ndarray, similar_results: list, top_n: int = 5):
    """可视化对比目标股票与相似股票的形态"""
    fig, axes = plt.subplots(top_n, 1, figsize=(12, 3*top_n), sharex=True)
    fig.suptitle(f"目标股票{TARGET_SYMBOL}与Top{top_n}相似股票形态对比", fontsize=14)
    
    # 绘制目标序列
    axes[0].plot(target_series, label=f"目标股票({TARGET_SYMBOL})", color="red", linewidth=2)
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # 绘制相似序列
    for i, res in enumerate(similar_results[:top_n]):
        axes[i].plot(res['window'], label=f"{res['symbol']} | 距离:{res['distance']:.4f}", 
                     color="blue", alpha=0.7)
        axes[i].set_title(f"第{i+1}名：{res['name']} | 形态区间：{res['start_date']}~{res['end_date']}")
        axes[i].legend()
        axes[i].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()

def main():
    # 1. 获取目标股票数据
    print(f"正在获取目标股票{TARGET_SYMBOL}的数据...")
    target_df = get_stock_data(TARGET_SYMBOL)
    if target_df is None:
        print(f"无法获取目标股票{TARGET_SYMBOL}的数据，请检查股票代码或网络连接")
        return
    
    # 2. 提取并标准化目标形态
    target_prices = target_df['收盘'].values[-LOOKBACK_DAYS:]
    scaler = MinMaxScaler()
    target_scaled = scaler.fit_transform(target_prices.reshape(-1, 1)).flatten()
    
    # 3. 获取全市场股票列表
    all_stocks = ak.stock_info_a_code_name()
    stock_dict = dict(zip(all_stocks['code'], all_stocks['name']))
    print(f"共获取到{len(all_stocks)}只A股股票，开始形态匹配...")
    
    # 4. 遍历全市场计算相似度
    similarities = []
    progress_bar = tqdm(all_stocks['code'].tolist(), desc="扫描进度")
    
    for symbol in progress_bar:
        try:
            df = get_stock_data(symbol)
            if df is None or len(df) < LOOKBACK_DAYS + PREDICT_DAYS:
                continue  # 跳过数据不足的股票
            
            # 滑动窗口遍历历史形态
            for i in range(len(df) - LOOKBACK_DAYS - PREDICT_DAYS + 1):
                window_prices = df['收盘'].values[i:i+LOOKBACK_DAYS]
                window_scaled = scaler.fit_transform(window_prices.reshape(-1, 1)).flatten()
                
                # 计算DTW距离
                dtw_distance = dtw.distance_fast(target_scaled, window_scaled)
                
                # 计算后续收益
                current_price = df['收盘'].values[i+LOOKBACK_DAYS-1]
                future_price = df['收盘'].values[i+LOOKBACK_DAYS+PREDICT_DAYS-1]
                future_return = (future_price / current_price - 1) * 100  # 转为百分比
                
                similarities.append({
                    'symbol': symbol,
                    'name': stock_dict.get(symbol, "未知"),
                    'distance': round(dtw_distance, 6),
                    'future_return(%)': round(future_return, 2),
                    'start_date': df.index[i].strftime('%Y-%m-%d'),
                    'end_date': df.index[i+LOOKBACK_DAYS-1].strftime('%Y-%m-%d'),
                    'window': window_scaled
                })
        except Exception as e:
            continue
    
    # 5. 按DTW距离排序，输出结果
    if not similarities:
        print("未找到任何相似形态的股票")
        return
    
    similarities_sorted = sorted(similarities, key=lambda x: x['distance'])
    top_similar = similarities_sorted[:SIMILAR_NUM]
    
    # 6. 打印结果表格
    print("\n" + "="*100)
    print(f"目标股票：{TARGET_SYMBOL}({stock_dict.get(TARGET_SYMBOL, '未知')}) | 分析周期：{LOOKBACK_DAYS}个交易日")
    print(f"共找到{len(similarities)}个相似形态，Top{SIMILAR_NUM}结果如下：")
    print("="*100)
    
    result_df = pd.DataFrame(top_similar).drop('window', axis=1)
    print(result_df.to_string(index=False))
    print("="*100 + "\n")
    
    # 7. 可视化形态对比
    plot_similar_stocks(target_scaled, top_similar, top_n=5)

if __name__ == "__main__":
    main()
