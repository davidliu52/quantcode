import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import pandas as pd
import numpy as np
import tensorflow as tf

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# 全部通过tf点调用，不单独导入keras模块
Sequential = tf.keras.Sequential
Dense = tf.keras.layers.Dense
Dropout = tf.keras.layers.Dropout

# 1. 数据加载与预处理
def load_and_preprocess_data(data_path):
    """
    加载并预处理股票数据
    """
    data = pd.read_csv(data_path)
    # 处理缺失值
    data = data.dropna()
    # 转换日期格式
    data['date'] = pd.to_datetime(data['date'])
    # 设置日期为索引
    data.set_index('date', inplace=True)
    return data

# 2. 因子计算
def calculate_factors(data):
    """
    计算各类价值因子
    """
    factors = pd.DataFrame(index=data.index)
    factors['PE'] = data['price'] / data['eps']
    factors['PB'] = data['price'] / data['book_value']
    factors['PS'] = data['price'] / data['sales']
    factors['DY'] = data['dividend'] / data['price']
    factors['EV_EBITDA'] = (data['market_cap'] + data['debt'] - data['cash']) / data['ebitda']
    return factors

# 3. 数据标准化
def standardize_data(factors, returns):
    """
    标准化因子和收益数据
    """
    # 因子标准化
    scaler = StandardScaler()
    factors_scaled = scaler.fit_transform(factors)
    
    # 收益标准化
    returns_scaled = (returns - returns.mean()) / returns.std()
    
    return factors_scaled, returns_scaled, scaler

# 4. 构建并训练模型
def train_model(factors, returns, epochs=50, batch_size=32):
    """
    训练因子组合模型
    """
    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        factors, returns, test_size=0.2, random_state=42)
    
    # 构建模型
    model = Sequential([
        Dense(64, activation='relu', input_shape=(factors.shape[1],)),
        Dropout(0.2),
        Dense(32, activation='relu'),
        Dense(1)
    ])
    
    # 编译模型
    model.compile(optimizer='adam',
                  loss='mse',
                  metrics=['mae'])
    
    # 训练模型
    history = model.fit(X_train, y_train,
                        epochs=epochs,
                        batch_size=batch_size,
                        validation_data=(X_test, y_test),
                        verbose=1)
    
    return model, history

# 5. 回测系统
class Backtester:
    """
    简单的回测系统
    """
    def __init__(self, model, data, scaler, initial_capital=100000):
        self.model = model
        self.data = data
        self.scaler = scaler
        self.initial_capital = initial_capital
        self.positions = {}
        
    def run_backtest(self, start_date, end_date):
        """
        运行回测
        """
        # 筛选回测期间的数据
        mask = (self.data.index >= start_date) & (self.data.index <= end_date)
        test_data = self.data[mask].copy()
        
        # 初始化投资组合
        portfolio_value = [self.initial_capital]
        current_cash = self.initial_capital
        
        # 按日回测
        for date, row in test_data.iterrows():
            # 取出因子并标准化
            factor_cols = ['PE', 'PB', 'PS', 'DY', 'EV_EBITDA']
            factor_df = row[factor_cols].to_frame().T
            factor_scaled = self.scaler.transform(factor_df)
            
            # 预测收益
            pred_ret = self.model.predict(factor_scaled, verbose=0)[0][0]
            
            # 交易逻辑 (简化版)
            if pred_ret > 0.5 and current_cash > 1000:
                # 买入
                amount = min(current_cash * 0.1, 10000)
                self.positions[row['symbol']] = amount / row['price']
                current_cash -= amount
            elif pred_ret < -0.5 and row['symbol'] in self.positions:
                # 卖出
                current_cash += self.positions[row['symbol']] * row['price']
                del self.positions[row['symbol']]
            
            # 计算当前持仓市值
            positions_value = 0
            for symbol, shares in self.positions.items():
                positions_value += shares * test_data.loc[date, 'price']
                
            portfolio_value.append(current_cash + positions_value)
        
        return portfolio_value

# 主程序
if __name__ == "__main__":
    # 1. 加载数据
    data = load_and_preprocess_data("stock_data.csv")
    
    # 2. 计算因子
    factors = calculate_factors(data)
    
    # 3. 计算未来收益 (作为目标变量)
    returns = data['price'].pct_change().shift(-1)  # 下期收益率
    
    # 移除无效数据
    valid_idx = ~(factors.isna().any(axis=1) | returns.isna())
    factors = factors[valid_idx]
    returns = returns[valid_idx]
    data_valid = data.loc[valid_idx.index].copy()
    
    # 【关键修复1】把因子合并到原始数据表，回测才能取到因子列
    data_valid = pd.concat([data_valid, factors], axis=1)
    
    # 4. 数据标准化
    factors_scaled, returns_scaled, scaler = standardize_data(factors, returns)
    
    # 5. 训练模型
    model, history = train_model(factors_scaled, returns_scaled)
    
    # 6. 回测（传入合并后带因子的数据集+标准化器）
    backtester = Backtester(model, data_valid, scaler)
    portfolio_values = backtester.run_backtest("2020-01-01", "2021-12-31")
    
    # 7. 可视化结果
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    plt.plot(portfolio_values)
    plt.title("神经网络因子选股策略-账户净值曲线")
    plt.xlabel("交易日")
    plt.ylabel("账户净值($)")
    plt.grid(alpha=0.3)
    plt.show()