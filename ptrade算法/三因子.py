"""
策略名称：
三因子日线交易策略
运行周期:
日线
策略流程：
盘前将中小板成分股中st、停牌、退市的股票过滤得到股票池
盘中：
1、获取市场风险溢价、市值因子、账面市值比因子三因子数据，
2、分组差值做线性回归处理，最终得到得分，选择得分高的标的调仓买入
3、每15天换仓一次
注意事项：
策略中调用的order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
# 导入函数库
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels import regression
from decimal import Decimal


# 初始化此策略
def initialize(context):
    g.factor_params_info = {
        'total_shareholder_equity': ['balance_statement', 'total_shareholder_equity'],#股东权益（资产负债表）
        'roe': ['profit_ability', 'roe']#净资产收益率（利润表）
    }
    set_params()  # 设置策参数调用函数，固定策略参数（调仓周期、持仓数量等）
    set_variables()  # 设置中间变量初始化全局中间变量（计数器、无风险利率、交易标记）
    if not is_trade():
        set_backtest()  # 设置回测条件


# 设置策参数
def set_params():
    g.tc =  1 # 调仓频率，调仓周期，每 15 个交易日换一次仓
    g.yb = 63  # 样本长度，因子回归样本长度，取过去 63 个交易日行情计算因子收益
    g.N = 10  # 持仓数目，持仓股票上限，策略始终最多持有 10 只个股
    g.NoF = 3  # 三因子模型，启用 3 个因子（RM 市场溢价、SMB 市值、HML 账面市值比）


# 设置中间变量
def set_variables():
    g.t = 0  # 记录连续回测天数，全局交易日计数器，用于判断是否到达 15 天调仓窗口
    g.rf = 0.04  # 无风险利率，年化无风险利率 4%，计算超额收益使用
    g.if_trade = False  # 当天是否交易，当日调仓开关，True 代表今日需要选股 + 买卖调仓


# 设置回测条件
def set_backtest():
    set_limit_mode('UNLIMITED')


# 每天盘前处理
def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime("%Y%m%d")#获取当日日期，转为YYYYMMDD字符串格式用于日期判断

    # 2005-06-01前回测由于数据不足，不执行。
    if g.current_date < '20050601':
        g.trade_flag = False
    else:
        g.trade_flag = True

    g.rf = 0.04#重置无风险利率，从沪深 300 指数000300.XBHS获取当日成分股作为初始股票池
    g.all_stocks = get_index_stocks('000300.XBHS', g.current_date)

    if g.t % g.tc == 0:
        # 每隔g.tc天，交易一次，计数器是 15 的倍数，触发调仓
        g.if_trade = True #标记今日需要选股、买卖
        # 将ST、停牌、退市三种状态的股票剔除当日的股票池
        g.all_stocks = filter_stock_by_status(g.all_stocks, filter_type=["ST", "HALT", "DELISTING"], query_date=None)
    g.t += 1


# 每天交易时要做的事情
def handle_data(context, data):
    if not g.trade_flag:
        return

    if g.if_trade:
        #取过去 63 日～前 1 日数据，计算每只股票三因子回归得分，63 个交易日之前的日期，回归样本起点，昨日，回归样本终点
        df_scores = get_scores(g.all_stocks, str(get_trading_day(-63)), str(get_trading_day(-1)), g.rf)
        # 为每个持仓股票分配资金
        # 依打分排序，当前需要持仓的股票
        if df_scores.empty:
            stock_sort = list()
        else:
            stock_sort = df_scores.sort_values('score')['code'].tolist()#按score升序排序股票，score 越高标的越优质
        # 把涨停状态的股票剔除
        up_limit_stock = get_limit_stock(stock_sort)['up_limit']
        # stock_sort = list(set(stock_sort)-set(up_limit_stock))
        stock_sort = [stock for stock in stock_sort if stock not in up_limit_stock]
        position_list = get_position_list(context)#获取当前全部持仓标的position_list
        print("持仓股票代码: %s" % position_list)
        # 持仓中跌停的股票不做卖出，查询持仓跌停股，跌停股票当日不卖出（无法成交）
        limit_info = get_limit_stock(position_list)
        hold_down_limit_stock = limit_info['down_limit']
        log.info('持仓跌停股：%s' % hold_down_limit_stock)
        position_list = get_position_list(context)
        # 持仓中除了不处于前g.N且跌停不能卖的股票进行卖出，现有持仓 - 新选股前 10 只 - 跌停股 = 需要全部卖出的股票

        sell_stocks = list(set(position_list) - set(stock_sort[:g.N]) - set(hold_down_limit_stock))
        # 对不在换仓列表中且飞跌停股的股票进行卖出操作，执行卖出：调用order_stock_sell对清仓股平掉全部仓位

        order_stock_sell(sell_stocks)
        # 获取仍在持仓中的股票
        position_list = get_position_list(context)
        # 获取调仓买入的股票，计算新增买入标的：选股前 10 只里，当前没有持仓的股票，补足至 10 只

        buy_stocks = [stock for stock in stock_sort if stock not in position_list][:(g.N - len(position_list))]
        # 仓位动态平衡的股票，新买入股票 + 保留持仓股票，剔除跌停股，总账户净值 / 10，每只目标持仓固定金额
        balance_stocks = list(set(buy_stocks + position_list) - set(hold_down_limit_stock))
        every_stock = context.portfolio.portfolio_value / g.N

        order_stock_balance(balance_stocks, every_stock)
    g.if_trade = False#调仓完成，重置g.if_trade=False，直到下一个 15 天周期



# 不在换仓目标中且没有跌停的股票进行清仓操作，遍历清仓列表，order_target_value(stock,0) 将个股持仓市值调整为 0，即全部卖出

def order_stock_sell(sell_stocks):
    # 对于不需要持仓的股票，全仓卖出
    for stock in sell_stocks:
        order_target_value(stock, 0)


# 非跌停的换仓目标股进行仓位再平衡，遍历目标持仓股票，统一调整持仓市值至every_stock（账户等权均分）

def order_stock_balance(balance_stocks, every_stock):
    for stock in balance_stocks:
        order_target_value(stock, every_stock)


# 获取综合得分
#
# 获取综合得分函数：核心FF三因子建模、个股alpha打分主函数
# 参数说明：
# stocks：待打分股票池列表
# begin：因子计算样本起始交易日
# end：因子计算样本结束交易日
# rf：年化无风险利率
def get_scores(stocks, begin, end, rf):
    # 使用try捕获全部计算异常，报错直接返回空DataFrame避免策略中断
    try:
        # 获取股票池总数量
        length = len(stocks)
        
        # 1、从估值表获取个股总市值total_value
        market_cap_df = get_fundamentals(stocks, 'valuation', fields='total_value', date=begin)
        # 删除存在空值的个股数据
        market_cap_df.dropna(inplace=True)

        # 判断市值数据表是否为空，无数据直接返回空表终止打分
        if market_cap_df.empty:
            print('获取市值数据失败，股票因子评分失败')
            return pd.DataFrame()
        
        # 2、调用封装函数读取股东权益财务因子数据
        total_shareholder_equity_df = get_factor_values(stocks, 'total_shareholder_equity', begin, g.factor_params_info)
        # 删除缺失财务数据的个股
        total_shareholder_equity_df.dropna(inplace=True)
        # 股东权益数据为空则返回空表，停止计算
        if total_shareholder_equity_df.empty:
            print('获取total_shareholder_equity财务数据失败，股票因子评分失败')
            return pd.DataFrame()
        
        # 3、读取ROE净资产收益率因子（本策略三因子未使用，预留扩展四因子RMW）
        roe_df = get_factor_values(stocks, 'roe', begin, g.factor_params_info)
        # 剔除ROE为空的数据行
        roe_df.dropna(inplace=True)
        # ROE数据缺失直接返回空表
        if roe_df.empty:
            print('获取roe财务数据失败，股票因子评分失败')
            return pd.DataFrame()
        
        # 将市值、股东权益、ROE三张因子表横向合并，按股票代码对齐
        df_all = pd.concat([market_cap_df, total_shareholder_equity_df, roe_df], axis=1)
        # 合并后任意因子缺失的个股全部剔除
        df_all.dropna(inplace=True)
        
        # 计算账面市值比BTM = 股东权益 / 股票总市值（价值因子核心指标）
        df_all['BTM'] = df_all['total_shareholder_equity'] / df_all['total_value']
        # 重置行索引，将股票代码index转为普通列，方便分组筛选
        df_all = df_all.reset_index()
        
        # 按总市值从小到大排序，取前1/3股票 = 小市值组合S
        S = df_all.sort_values('total_value')['index'][:int(length / 3)]
        # 按总市值从小到大排序，取后1/3股票 = 大市值组合B
        B = df_all.sort_values('total_value')['index'][length - int(length / 3):]
        # 按BTM账面市值比从小到大排序，取前1/3 = 低价值组合L
        L = df_all.sort_values('BTM')['index'][:int(length / 3)]
        # 按BTM账面市值比从小到大排序，取后1/3 = 高价值组合H
        H = df_all.sort_values('BTM')['index'][length - int(length / 3):]
        # 按ROE从小到大排序，取前1/3 = 低盈利组合W
        W = df_all.sort_values('roe')['index'][:int(length / 3)]
        # 按ROE从小到大排序，取后1/3 = 高盈利组合R
        R = df_all.sort_values('roe')['index'][length - int(length / 3):]

        # 批量获取股票池内所有个股[begin,end]区间日线收盘价，返回字典格式
        close_data = get_price(stocks, begin, end, fields='close', frequency='1d', is_dict=True)

        # 新建空DataFrame，用于统一存放所有股票收盘价时间序列
        close_df = pd.DataFrame()
        # 循环遍历每只股票的行情数据
        for stock_code, stock_data in close_data.items():
            # 将字符串日期转为标准datetime时间索引
            date_info = pd.to_datetime(stock_data['datetime'], format='%Y%m%d')
            # 提取当日收盘价序列
            close_info = stock_data['close']
            # 以日期为索引，单只股票收盘价作为一列存入总表
            close_df[stock_code] = pd.Series(close_info, index=date_info)
        # 按交易日期升序排列整个价格表
        close_df.sort_index(inplace=True)
        
        # 对数收益率计算：log(Pt) - log(Pt-1)，np.diff实现差分
        # +0*close_df[1:]仅用于对齐维度，无实际数值运算
        df = np.diff(np.log(close_df), axis=0) + 0 * close_df[1:]
        
        # 计算市值因子SMB：小盘股日均收益均值 - 大盘股日均收益均值
        SMB = df[S].T.sum() / len(S) - df[B].T.sum() / len(B)
        # 计算价值因子HML：高BTM组合收益均值 - 低BTM组合收益均值
        HML = df[H].T.sum() / len(H) - df[L].T.sum() / len(L)
        # 计算盈利因子RMW：高ROE组合收益均值 - 低ROE组合收益均值（四因子备用）
        RMW = df[R].T.sum() / len(R) - df[W].T.sum() / len(W)
        
        # 获取沪深300指数同期日线收盘价，用于构建市场风险溢价因子RM
        dp = get_price('000300.XSHG', begin, end, '1d')['close']
        # 校验指数行情与个股行情时间长度是否匹配，差值大于1判定数据缺失
        if len(dp)-len(df)>1:
            log.info('历史行情数据缺失，股票因子评分失败')
            # 数据长度不一致，直接返回空表终止打分
            return pd.DataFrame()
        # 市场超额收益RM = 指数对数收益率 - 日度无风险利率(年化rf/252交易日)
        RM = np.diff(np.log(dp)) - rf / 252
        
        # 整合四大因子时间序列，构建自变量矩阵X
        X = pd.DataFrame({"RM": RM, "SMB": SMB, "HML": HML, "RMW": RMW})
        # 根据全局参数g.NoF截取前N个因子，策略为三因子则只取RM、SMB、HML
        factor_flag = ["RM", "SMB", "HML", "RMW"][:g.NoF]
        # 筛选实际参与回归的因子列
        X = X[factor_flag]
        
        # 初始化得分列表，长度与股票池数量一致，初始值0.0
        t_scores = [0.0] * length
        # 遍历每一只股票，逐个做线性回归计算alpha得分
        for i in range(length):
            # 获取当前循环个股代码
            t_stock = stocks[i]
            # 个股超额收益 = 个股收益率 - 日无风险利率，与因子矩阵X做OLS回归
            # linreg返回[截距alpha, 各因子系数]
            t_r = linreg(X, df[t_stock] - rf / 252, len(factor_flag))
            # 将回归截距alpha作为个股综合打分score
            t_scores[i] = t_r[0]
        
        # 组装股票代码+对应打分的结果数据表
        scores = pd.DataFrame({'code': stocks, 'score': t_scores})
        # 按score得分升序排序（数值越大，超额收益能力越强）
        df_scores = scores.sort_values(by='score')
        # 返回全部股票打分结果表
        return df_scores
    # 捕获函数内部所有报错（数据缺失、维度错误、计算异常等）
    except:
        # 打印错误提示日志
        print('股票因子评分失败，请检查数据')
        # 异常发生返回空DataFrame，上层handle_data会判定无选股标的，当日不调仓
        return pd.DataFrame()


# 获取因子值
def get_factor_values(stock_list, factor, date, factor_params_info):
    """
    获取因子值方法
    入参：
    1、股票池：stock_list
    2、因子名称：factor
    3、计算日期：date
    4、因子数据获取需要维护的信息（因子名称、表名、字段名）
    """
    data = get_fundamentals(stock_list, table=factor_params_info[factor][0], fields=factor_params_info[factor][1],
                            date=date, is_dataframe=True)
    factor_info = {}
    for stock in stock_list.copy():
        if stock not in data.index:
            continue
        factor_info[stock] = data.loc[stock, factor_params_info[factor][1]]
    if factor_info == {}:
        return pd.DataFrame()
    factor_df = pd.DataFrame.from_dict(factor_info, orient='index')
    factor_df.columns = [factor_params_info[factor][1]]
    return factor_df


# 线性回归
def linreg(x, y, columns=3):
    x = sm.add_constant(np.array(x))
    y = np.array(y)
    if len(y) > 1:
        results = regression.linear_model.OLS(y, x).fit()
        return results.params
    else:
        return [float("nan")] * (columns + 1)


# 保留小数点两位
def replace(x):
    x = Decimal(x)
    x = float(str(round(x, 2)))
    return x


# 生成昨日持仓股票列表
def get_position_list(context):
    return [
        position.sid
        for position in context.portfolio.positions.values()
        if position.amount != 0
    ]


# 日级别回测获取持仓中不能卖出的股票(涨停就不卖出)
def get_limit_stock(stock_list):
    out_info = {'up_limit': [], 'down_limit': []}
    for stock in stock_list:
        limit_status = check_limit(stock)[stock]
        if limit_status == 1:
            out_info['up_limit'].append(stock)
        elif limit_status == -1:
            out_info['down_limit'].append(stock)
    return out_info