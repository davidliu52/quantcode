

# 根据情况指定xtquant的路径
import pandas as pd
import numpy as np
# 显示出所有列
pd.set_option('display.max_columns', None)
import matplotlib.pyplot as plt
# 显示中文正常
plt.rcParams['font.sans-serif'] = ['SimHei']
import concurrent.futures
from xtquant import xtdata
xtdata.reconnect()
import xtquant
print(xtquant)
print(xtdata.data_dir)
# 指定获取投研端数据(可不指定，默认优先连接投研)
# xtdata.reconnect(port=58612)
# xtdata.download_sector_data()
#try
class G():
    pass


g = G()



# def on_backtest_finished(C):
#     """该函数会在回测结束后被调用"""
#     get_backtest_index(C.request_id, r'C:\Users\david\Documents\QMT投研版教程\01_小市值策略\原生Python_小市值_多进程\index') # 导出绩效到指定文件夹，文件名自动生成，如果同时运行多个，需要填写不同的文件夹路径
#     get_group_result(C.request_id, r'C:\Users\david\Documents\QMT投研版教程\01_小市值策略\原生Python_小市值_多进程\result',['position', 'order', 'deal' ])# 导出[持仓，委托，成交]信息到指定文件夹，文件名自动生成，如果同时运行多个，需要填写不同的文件夹路径

def init(C):
    #init handlebar函数的入参是ContextInfo对象 可以缩写为C
	#设置测试标的为主图品种
	# C.stock= C.stockcode + '.' +C.market
    C.stock = '600050.SH'
    #line1和line2分别为两条均线期数
    # C.line1=34   #快线参数
    # C.line2=89   #慢线参数
    C.line1=C._param.get('n1', 25)   #快线参数
    C.line2=C._param.get('n2', 120)   #慢线参数
    #accountid为测试的ID 回测模式资金账号可以填任意字符串
    C.accountid = "testS"

def handlebar(C):
    #当前k线日期
	bar_date = timetag_to_datetime(C.get_bar_timetag(C.barpos), '%Y%m%d%H%M%S')
    #回测不需要订阅最新行情使用本地数据速度更快 指定subscribe参数为否. 如果回测多个品种 需要先下载对应周期历史数据
	local_data = C.get_market_data_ex(['close'], [C.stock], end_time = bar_date, period = C.period, count = max(C.line1, C.line2), subscribe = False)
	close_list = list(local_data[C.stock].iloc[:, 0])
	#将获取的历史数据转换为DataFrame格式方便计算
	#如果目前未持仓，同时快线穿过慢线，则买入8成仓位
	if len(close_list) <1:
		print(bar_date, '行情不足 跳过')
	line1_mean = round(np.mean(close_list[-C.line1:]), 2)
	line2_mean = round(np.mean(close_list[-C.line2:]), 2)
	# print(f"{bar_date} 短均线{line1_mean} 长均线{line2_mean}")
	account = get_trade_detail_data('test', 'stock', 'account')
	account = account[0]
	available_cash = int(account.m_dAvailable)
	holdings = get_trade_detail_data('test', 'stock', 'position')
	holdings = {i.m_strInstrumentID + '.' + i.m_strExchangeID : i.m_nVolume for i in holdings}
	holding_vol = holdings[C.stock] if C.stock in holdings else 0
	if holding_vol == 0 and line1_mean > line2_mean:
		vol = int(available_cash / close_list[-1] / 100) * 100
		#下单开仓
		passorder(23, 1101, C.accountid, C.stock, 5, -1, vol,'',0,'', C)
		# print(f"{bar_date} 开仓")
		# C.draw_text(1, 1, '开')
	#如果目前持仓中，同时快线下穿慢线，则全部平仓
	elif holding_vol > 0 and line1_mean < line2_mean:
		#状态变更为未持仓
		C.holding=False
		#下**仓
		passorder(24, 1101, C.accountid, C.stock, 5, -1, holding_vol,'',0,'', C)
		# print(f"{bar_date} 平仓")
		# C.draw_text(1, 1, '平')

def run_strategy(lock, user_script, param):
    # xtdata.connect(port=58610)

    from xtquant.qmttools import run_strategy_file
    ret = run_strategy_file(user_script, param)
    # print(ret)
    if ret:
        # 提取净值数据
        df = ret.get_backtest_index()[['时间', '单位净值']]
        # 获取 C._param 中的参数n,替换单位净值
        n1 = param['n1']
        n2 = param['n2']
        # print(n1,n2)
        df.rename(columns={'单位净值': f'档位_{n1}_{n2}'}, inplace=True)
        return df
    return None



if __name__ == '__main__':
    import sys
    import time
    from xtquant.qmttools import run_strategy_file
    import concurrent
    import concurrent.futures
    import matplotlib.pyplot as plt
    import multiprocessing

    # 回测参数设置
    detail = {
        "asset": 100_0000.0  # 初始资金
        , "margin_ratio": 0.05  # 保证金比例（期货用）

        , "slippage_type": 1  # 滑点类型 0 按最小变动价跳数；  1：按固定值；2：按成交额比例。
        , "slippage": 0
        # 滑点 说明 当slippage_type=0,slippage=1,表示每股滑点是1跳（下100股会直接造成100*0.01=1元亏损）；slippage_type=1,slippage=1 表示每股滑点是1元（下100股会直接造成100元亏损）；slippage_type=2,slippage=0.05 表示每笔交易的滑点比例为5%
        , "max_vol_rate": 0.0  # 最大成交比例
        # comsisson_type说明 0 按成交额比例； 1 按固定值
        # 该值影响 open_commission close_commission close_today_commission
        , "comsisson_type": 0  # 手续费类型 0 按成交额比例； 1 按固定值
        # 买入印花税， 单位永远是比例，0.0001表示万 1的手续费 # 股票生效，期货不生效
        , "open_tax": 0

        # 卖出印花税，单位永远是比例， 0.0001表示万 1的手续费 # 股票生效，期货不生效
        , "close_tax": 0

        # 最小手续费  #单位永远是元 设置成1 股票表示每股扣除1元,# 股票生效，期货不生效
        , "min_commission": 0

        # 买入/开仓手续费  comsisson_type选0 ，0.0001表示万 1的手续费 comsisson_type选1 单位就是元。 股票、期货生效
        # 单位是元时，股票表示每股扣1元，期货表示每手1元
        , "open_commission": 0  # 0.00085

        # 卖出手续费 comsisson_type选0 ，0.0001表示万 1的手续费 comsisson_type选1 单位就是元。 股票表示卖出、期货表示平昨
        # 单位是元时，股票表示每股扣1元，期货表示每手1元
        , "close_commission": 0

        # 平今手续费  comsisson_type选0 ，0.0001表示万 1的手续费 comsisson_type选1 单位就是元。股票不生效,期货表示平今
        # 单位是元时，股票表示每股扣1元，期货表示每手1元
        , "close_today_commission": 0

        # 业绩比较基准
        , "benchmark": '000300.SH'

    }
    param_list = [
        {
        'stock_code': '600050.SH',  # 驱动handlebar的代码,
        'period': '1d',  # 策略执行周期 即主图周期
        'start_time': '2004-01-01 00:00:00',  # 注意格式，不要写错
        'end_time': '2023-12-31 00:00:00',  # 注意格式，不要写错
        'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
        'quote_mode': 'history',
        'backtest': detail,
        'n1': 60,
        'n2': 220
        # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realtime
    },
    {
        'stock_code': '600050.SH',  # 驱动handlebar的代码,
        'period': '1d',  # 策略执行周期 即主图周期
        'start_time': '2004-01-01 00:00:00',  # 注意格式，不要写错
        'end_time': '2023-12-31 00:00:00',  # 注意格式，不要写错
        'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
        'quote_mode': 'history',
        'backtest': detail,
        'n1': 30,
        'n2': 80
        # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realtime
    },
    {
        'stock_code': '600050.SH',  # 驱动handlebar的代码,
        'period': '1d',  # 策略执行周期 即主图周期
        'start_time': '2004-01-01 00:00:00',  # 注意格式，不要写错
        'end_time': '2023-12-31 00:00:00',  # 注意格式，不要写错
        'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
        'quote_mode': 'history',
        'backtest': detail,
        'n1': 10,
        'n2': 50
        # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realtime
    },
    {
        'stock_code': '600050.SH',  # 驱动handlebar的代码,
        'period': '1d',  # 策略执行周期 即主图周期
        'start_time': '2024-01-01 00:00:00',  # 注意格式，不要写错
        'end_time': '2023-12-31 00:00:00',  # 注意格式，不要写错
        'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
        'quote_mode': 'history',
        'backtest': detail,
        'n1': 18,
        'n2': 120
        # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realtime
    },

    ]
    print(len(param_list))
    # user_script = os.path.basename(__file__)  # 当前脚本路径，相对路径，绝对路径均可,此处为相对路径的方法
    user_script = sys.argv[0]  # 当前脚本路径，相对路径，绝对路径均可，此处为绝对路径的方法

    t0 = time.time()

    lock = multiprocessing.Manager().Lock()
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_strategy, lock, user_script, param_list[i]): i for i in range(len(param_list))}

    dfs = []
    for future in concurrent.futures.as_completed(futures):
        res = future.result()
        if res is not None:
            """
            # 提取净值数据
            df = res.get_backtest_index()[['时间', '单位净值']]
            """
            # 修改列名 单位净值 为 index
            df = res
            # 设置时间为索引，调整时间格式，'%Y%m%d%H%M%S' -> '%Y-%m-%d %H:%M:%S'
            df['时间'] = pd.to_datetime(df['时间'], format='%Y%m%d%H%M%S')
            df.set_index('时间', inplace=True)
            # 合并到总的 DataFrame 中
            # df_all = pd.concat([df_all, df], axis=1)
            dfs.append(df)

    df_all = pd.concat(dfs, axis=1)
    print(f"执行完毕 {time.time() - t0}")
    print(df_all)
    print("执行完毕")

    df = df_all
    print(df.head())
    # exit()


    # 创建一个图形和子图
    fig, ax = plt.subplots(figsize=(10, 6))

    # 使用 ax 对象绘制每个策略的净值曲线
    for strategy in df.columns:
        ax.plot(df.index, df[strategy], label=strategy)

    # 设置标题、坐标轴标签和图例
    ax.set_title('净值曲线比较')
    ax.set_xlabel('时间')
    ax.set_ylabel('单位净值')
    ax.legend()

    # 显示图形
    plt.show()