"""
策略名称：
阳线策略
注意事项：
策略中调用的order_target、order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import numpy as np
from decimal import Decimal
from datetime import datetime

# =========【新增：平台模拟环境，原始代码无】========
class GlobalObj:
    pass
g = GlobalObj()

class LogMock:
    @staticmethod
    def info(msg):
        print(msg)
log = LogMock()

set_fixed_slippage = lambda x: None
set_slippage = lambda slippage: None
set_limit_mode = lambda x: None

def is_trade():
    return False

class MockContext:
    def __init__(self):
        self.blotter = type("Blotter",(),{"current_dt":datetime(2025,6,6)})
        class Portfolio:
            positions = {}
            portfolio_value = 1000000
        self.portfolio = Portfolio()

# 模拟data行情数据对象
class MockBar:
    def __init__(self):
        self.open = 10
        self.close = 12
def make_mock_data(stock_list):
    d = {}
    for s in stock_list:
        d[s] = MockBar()
    return d

def get_history(n, frequency, field, security_list, fq, include, is_dict):
    res = {}
    for code in security_list:
        arr = []
        for i in range(n):
            if i == n-1:
                close = 8; op =10
            else:
                close=11; op=9
            arr.append({"open":op,"close":close,"volume":1000,"low":7})
        res[code] = arr
    return res

def get_stock_status(codelist, tp):
    d = {c:False for c in codelist}
    return d

mock_k_num = 0
def get_current_kline_count():
    return mock_k_num

def get_snapshot(code):
    return {code:{"last_px":12}}

def check_limit(code):
    return {code:0}

def order_target(code, num):
    print(f"【清仓 {code},目标持仓:{num}】")

def order_target_value(code, val):
    print(f"【买入 {code},目标市值:{val:.2f}】")

def get_Ashares():
    return ["001","002","003"]
# ==============================================

# ----------------下面全部是【你的原始策略源码，无修改】----------------
def initialize(context):
    if is_trade():
        log.info('-----trade-------')
    else:
        set_fixed_slippage(0.0)
        set_slippage(slippage=0.01)
        set_limit_mode('UNLIMITED')
    g.before_start = False
    # 持仓数量
    g.hold_num = 10


def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime("%Y%m%d")
    # 持仓股昨日最低价容器
    g.holds_pre_low_price = {}
    # 今日开盘价容器
    g.open_price_info = {}
    # 昨日持仓股
    g.position_list = []
    # 获取全市场股票，选最近10个交易日K线，判断个股形态：最近的一个阴K线之后没有阳线结构，符合形态且当天没有停牌的就加入股票池
    g.stock_list = get_Ashares()

    his_data_info = get_history(10, frequency='1d', field=['open', 'close', 'volume'],
                                security_list=g.stock_list, fq=None, include=False, is_dict=True)
    halt_status = get_stock_status(g.stock_list, 'HALT')
    g.buy_stocks = []
    for stock in g.stock_list.copy():
        # 停牌的过滤
        if halt_status[stock]:
            continue
        his_data = his_data_info[stock]
        his_data = np.array(list(filter(volume_filter, his_data)))
        if len(his_data) < 2:
            continue
        yinx_flag = False
        yangx_flag = False
        is_true = False
        for stock_data in reversed(his_data):
            if stock_data['close'] < stock_data['open']:
                yinx_flag = True
            if stock_data['close'] > stock_data['open']:
                yangx_flag = True
            if yinx_flag and not yangx_flag:
                is_true = True
                break
            if not yinx_flag and yangx_flag:
                is_true = False
                break
        if is_true:
            g.buy_stocks.append(stock)
    g.before_start = True
    g.first_handledata = False
    total_value = context.portfolio.portfolio_value
    g.cash = total_value / g.hold_num

    # 对持仓进行数据载入
    g.position_list = position_last_close_init(context)
    log.info(('盘前查询持仓股:', g.position_list))
    log.info(len(g.position_list))
    # 判断持仓股是否停牌，停牌的标的当日不做交易判断
    halt_status = get_stock_status(g.position_list, 'HALT')
    #【仅此处补include=False，其余原样】
    pre_low_data = get_history(1, '1d', 'low', security_list=g.position_list, fq='dypre', include=False, is_dict=True)
    for stock in g.position_list.copy():
        # 停牌的过滤
        if halt_status[stock]:
            g.position_list.remove(stock)
            continue
        # 非停牌持仓股获取昨日最低价
        g.holds_pre_low_price[stock] = pre_low_data[stock]['low'][0]


def handle_data(context, data):
    global mock_k_num
    # 确保盘前处理已完成
    if not g.before_start:
        return
    g.K_num = get_current_kline_count()
    # 第一分钟处理
    if not g.first_handledata:
        # 回测场景持仓股及拟买股票池赋值开盘价
        if not is_trade():
            for stock in g.buy_stocks:
                g.open_price_info[stock] = data[stock].open
            for stock in g.position_list:
                g.open_price_info[stock] = data[stock].open
        g.first_handledata = True

    # 14:45之前持仓股如果符合最新价小于昨日最低价条件清仓
    if g.K_num < 225:
        if is_trade():
            for stock in g.position_list.copy():
                snapshot = get_snapshot(stock)
                if snapshot[stock]['last_px'] < g.holds_pre_low_price[stock]:
                    order_target(stock, 0)
                    g.position_list.remove(stock)
        else:
            for stock in g.position_list.copy():
                if data[stock].close < g.holds_pre_low_price[stock]:
                    order_target(stock, 0)
                    g.position_list.remove(stock)

    # 14:45分对非涨停状态的个股进行清仓
    if g.K_num == 225:
        for stock in g.position_list.copy():
            stock_flag = check_limit(stock)[stock]
            if stock_flag != 1:
                order_target(stock, 0)
                g.position_list.remove(stock)

    # 14:50分进行买入,校验当日实体阳线K线
    if g.K_num == 230:
        hold_list = position_last_close_init(context)
        if is_trade():
            count = 0
            for stock in g.buy_stocks:
                if count + len(hold_list) < g.hold_num and stock not in hold_list:
                    snapshot = get_snapshot(stock)
                    if snapshot[stock]['last_px'] > g.open_price_info[stock]:
                        order_target_value(stock, g.cash)
                        count += 1
        else:
            count = 0
            for stock in g.buy_stocks:
                if count + len(hold_list) < g.hold_num and stock not in hold_list:
                    if data[stock].close > g.open_price_info[stock]:
                        order_target_value(stock, g.cash)
                        count += 1


# 生成持仓股票列表
def position_last_close_init(context):
    position_last_list = []
    for stock in context.portfolio.positions:
        if context.portfolio.positions[stock].amount != 0:
            position_last_list.append(stock)
    return position_last_list


# 保留小数点两位
def replace(x):
    x = Decimal(x)
    x = float(str(round(x, 2)))
    return x


# 按成交量筛选停牌的数据
def volume_filter(data):
    if data['volume'] > 0:
        return data

# =========主运行代码（修改：不再传None，传入模拟data）========
if __name__ == '__main__':
    ctx = MockContext()
    all_stock = get_Ashares()
    mock_data = make_mock_data(all_stock)

    initialize(ctx)
    print("=====初始化完成=====\n")

    before_trading_start(ctx, mock_data)
    print("=====盘前选股完毕，候选买入池：", g.buy_stocks,"=====\n")

    for mock_k_num in [1,5,10]:
        handle_data(ctx, mock_data)

    mock_k_num = 225
    handle_data(ctx, mock_data)

    mock_k_num = 230
    handle_data(ctx, mock_data)

    print("\n【当日收盘汇总：读取全局g全部数据】")
    print(f"当日日期g.current_date：{g.current_date}")
    print(f"预设最大持仓数量g.hold_num：{g.hold_num}")
    print(f"单只买入资金g.cash：{g.cash:.2f}")
    print(f"盘前筛选备选股票池g.buy_stocks：{g.buy_stocks}")
    print(f"个股开盘价缓存g.open_price_info：{g.open_price_info}")
    print(f"持仓止损昨日低价g.holds_pre_low_price：{g.holds_pre_low_price}")