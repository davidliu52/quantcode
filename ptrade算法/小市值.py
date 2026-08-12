"""
策略名称：
小市值日线交易策略
运行周期:
日线
策略流程：
盘前将中小板综成分股中st、停牌、退市的股票过滤得到股票池
盘中换仓，始终持有当日流通市值最小的股票（涨停标的不换仓）。
注意事项：
策略中调用的order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""


# 初始化
def initialize(context):
    # 设置基准指数
    set_benchmark("000300.XSHG")
    # 股票池对应指数代码
    g.index = "399101.XBHS"# 中小板综
    # 持有股票数量
    g.buy_stock_count = 6
    # 筛选股票数量
    g.screen_stock_count = 10
    if not is_trade():
        set_backtest()  # 设置回测条件

    # ==========新增：当日是否已经调仓标志==========
    g.has_traded_today = False
    
    if not is_trade():
        set_backtest()  # 设置回测条件
# 设置回测条件
def set_backtest():
    set_limit_mode("UNLIMITED")

# 盘前处理
def before_trading_start(context, data):
    g.has_traded_today = False

    g.pre_position_list = list(get_positions().keys()) # 获取上一日持仓股票代码列表，存入全局变量，用于后续判断持仓涨停个股
    
    log.info("上一日持仓股票代码: %s" % g.pre_position_list)
    
    g.stock_list = get_index_stocks(g.index)    # 根据指数代码获取指数全部成分股列表（中小板综所有成份股）
    
    log.info("大盘中所有股份的数量: %s" % len(g.stock_list))    #获得创业版的所有股份的数量
    
    # 指数成分股按昨日收盘时的流通市值进行从小到大排序，截取市值最小的100个标的进行股票状态筛选（考虑回测速度）
    # 获取基本面估值数据：成分股的总市值、流通A股、流通市值
    # date=context.previous_date 使用前一个交易日数据，避免未来函数
    # sort_values(by="float_value") 按照【昨日流通市值】从小到大排序
    # head(100) 只取市值最小100只，减少数据计算量，提升回测速度
    
    log.info("前一个交易日的日期: %s" % context.previous_date)   
    df = get_fundamentals(g.stock_list, "valuation", fields=["total_value", "a_floats", "float_value"],
                          date=context.previous_date).sort_values(by="float_value").head(100)
    stock_list_tmp = df.index.tolist()
    
    # 将ST、停牌、退市三种状态的股票剔除当日的股票池
    stock_list_tmp = filter_stock_by_status(stock_list_tmp, filter_type=["ST", "HALT", "DELISTING"], query_date=None)
    df = df[df.index.isin(stock_list_tmp)]#只保留行索引存在于股票列表 stock_list_tmp 里的数据，剔除不在列表内的行。
    g.df = df.head(g.screen_stock_count)
    log.info("最小的10个股票是什么: %s" % g.df.index.tolist()) # 保留状态筛选后的股票，并取其中流通市值最小的10个股票

# 盘中处理
#handle_data 函数运行时，先调用 get_trade_stocks 函数算出当日目标持仓股票列表，买入调仓操作。
#打印目标持仓清单日志，再将目标持仓列表传入 trade 函数，由 trade 函数根据目标清单执行对应的卖出、

def handle_data(context, data):

    buy_stocks = get_trade_stocks(context, data)    # 调用函数计算今日目标持仓列表

    log.info("buy_stocks:%s" % buy_stocks)    # 日志打印目标买入股票清单

    trade(context, buy_stocks)    # 执行调仓买卖逻辑


# 交易函数
#该交易函数首先遍历账户全部持仓，将不在当日目标持仓清单 buy_stocks 内的个股全部委托清仓；
#随后筛选出账户中实际持有筹码的标的统计现有持仓数量，若当前持仓只数小于预设目标持股数量，则把账户可用现金平均分配给剩余可开仓名额，接着遍历目标股票池，
#对其中尚未持仓的个股下达委托，将其持仓市值调整至均分后的目标金额，完成等额建仓。
def trade(context, buy_stocks):

    #不在今日目标持仓列表里的老持仓，全部卖出；留在目标列表中的持仓，则继续持有不操作。
    log.info("持仓内容 %s"% len(context.portfolio.positions))
    for stock in context.portfolio.positions:
        if stock not in buy_stocks:      # 如果当前持仓个股不在今日目标持仓列表，则清仓
            order_target_value(stock, 0)
            log.info("sell:%s" % stock)

    # ---------------------- 第二步：统计现有持仓，计算剩余可买入名额 ----------------------
    # 提取当前所有有仓位的股票代码
    position_list = [position.sid for position in context.portfolio.positions.values()
                     if position.amount != 0]
    position_count = len(position_list)
    
    # 如果当前持仓数量 < 目标持仓数量，说明还有仓位可以买入新股
    log.info("当前仓位的数量 %s"% position_count)
    if g.buy_stock_count > position_count:
        value = context.portfolio.cash / (g.buy_stock_count - position_count) # 剩余现金平均分配给剩余买入名额
        log.info("要买的股票的数量 %s"% len(buy_stocks))   # 遍历目标股票池
        for stock in buy_stocks:
            if stock not in context.portfolio.positions:  # 只买入目前没有持仓的标的
                order_target_value(stock, value)          # 调整仓位至目标金额，实现等额建仓


# 获取买入股票池（涨停股不参与换仓）

#该函数首先检索上一交易日持仓个股，识别其中当日涨停标的并予以保留不卖出；
#接着读取盘前初步筛选得到的候选股票清单，利用盘中实时成交价结合历史流通股本实时计算候选股最新流通市值，
#剔除价格异常标的后按实时流通市值从小到大排序；随后用目标持仓总数减去涨停持仓数量，得到可新增买入个股名额，
#选取排序后市值最小对应数量的个股，最后将新筛选个股与原有涨停持仓合并，形成当日完整目标持仓清单，
#实现持仓涨停股票不参与轮换、仅对其余仓位轮换配置实时流通市值更小标的的效果。

# 获取买入股票池（涨停股不参与换仓）
def get_trade_stocks(context, data):
        
        # ===================== 新增：股票代码格式转换工具函数 =====================
    def to_limit_code(stock_code):
        """原生代码 XSHG/XSHE → check_limit 使用的 SS/SZ 格式"""
        return stock_code.replace("XSHG", "SS").replace("XSHE", "SZ")

    def to_platform_code(limit_code):
        """SS/SZ 格式转回平台原生 XSHG/XSHE（本策略暂时用不到，预留扩展）"""
        return limit_code.replace("SS", "XSHG").replace("SZ", "XSHE")
        
    # 遍历昨日持仓，检查哪些股票涨停， check_limit 判断涨跌停；涨停返回1。replace 代码格式转换（聚宽部分接口代码后缀区分SH/SZ、SS/SZ）
    hold_up_limit_stock = [stock.replace("XSHG", "SS").replace("XSHE", "SZ") for stock in g.pre_position_list if check_limit(stock)[stock] == 1]
   
    df = g.df # 取出盘前筛选好的10只候选股DataFrame，市面上所有的都遍历之后找出的流通性最小的
    
    log.info("涨停的股票的数量 %s"% len(hold_up_limit_stock))#前日持仓中涨停的股票的数量
    
    # 如果候选股票池为空，直接返回持仓涨停个股（只保留涨停股，其余全部卖出）
    if df.empty:
        return hold_up_limit_stock
    # 将索引（股票代码）新增为单独一列code
    df["code"] = df.index
    # 计算当时最新的流通市值（昨日的流通股本*最新价）
    df["curr_float_value"] = df.apply(lambda x: x["a_floats"] * data[x["code"]].price, axis=1)
    # 剔除流通市值等于0的异常数据（防止停牌无价格造成计算错误）
    df = df[df["curr_float_value"] != 0]

    # ============【新增逻辑开始】剔除候选池中当日涨停标的，禁止新开仓买入============
    def is_today_up_limit(code):    # 过滤：移除当日涨停股票，不能新开仓
        # check_limit检测是否涨停
        limit_info = check_limit(code)
        return limit_info.get(code, 0) == 1

    df = df[~df["code"].apply(is_today_up_limit)]
    log.info("剔除当日涨停候选股后10个剩余候选数量：%s" % len(df))
    # ============【新增逻辑结束】====================================================

    stocks = df.sort_values(by="curr_float_value").index.tolist()#都剔除后的候选的进行排序选小的几个
    log.info("排序后他的股票的数量：%s" % len(stocks))

    # 可新增非涨停股票数量 = 目标持仓总数5 - 持仓中涨停个股数量
    # 原理：涨停个股不能卖出，需要保留原有仓位
    count = g.buy_stock_count - len(hold_up_limit_stock)    # 计算本次拟买入的数量（最大持仓量-持仓中涨停的数量（因为涨停股不卖））

    count = max(count, 0)    # 防止count负数兜底保护

    check_out_lists = stocks[:count]    # 选取实时市值最小的count只新股

    check_out_lists = check_out_lists + hold_up_limit_stock    # 合并【新选出小盘股 + 原有持仓涨停股】构成完整目标持仓池
    return check_out_lists