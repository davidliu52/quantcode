import xtquant.xtdata as xtdata

# 模拟上下文，脱离策略框架测试
class MockContext:
    def __init__(self):
        self.previous_date = "2026-07-17"

context = MockContext()
stock_list = ["000001.SZ", "600036.SH", "601318.SH"]

# 你的原查询语句
df = xtdata.get_fundamentals(
    stock_list,
    "valuation",
    fields=["total_value", "a_floats", "float_value"],
    date=context.previous_date
).sort_values(by="float_value")

print(df)