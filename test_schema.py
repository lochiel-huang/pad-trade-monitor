from schema import Employee, Trade, Department, AccessLevel, TradeSide
from datetime import date, time

# 建個測試員工
emp = Employee(
    employee_id="EMP0001",
    name="Alice Chan",
    department=Department.RESEARCH,
    role="Senior Analyst",
    access_level=AccessLevel.HIGH,
    covered_stocks=["0700.HK", "9988.HK"],
    hire_date=date(2022, 6, 1)
)
print(emp.model_dump_json(indent=2))

# 建個測試交易
trade = Trade(
    trade_id="TRD00001",
    employee_id="EMP0001",
    ticker="0700.HK",
    side=TradeSide.BUY,
    quantity=1000,
    trade_date=date(2026, 6, 10),
    trade_time=time(10, 30),
    price=460.0,
    pre_cleared=False
)
print(trade.model_dump_json(indent=2))

# 測試validator:pre_cleared=True 但沒有ID應該爆炸
try:
    bad = Trade(
        trade_id="TRD00002",
        employee_id="EMP0001",
        ticker="0700.HK",
        side=TradeSide.BUY,
        quantity=500,
        trade_date=date(2026, 6, 10),
        trade_time=time(10, 30),
        price=460.0,
        pre_cleared=True  # 但沒給 pre_clearance_id
    )
except Exception as e:
    print(f"\n預期的錯誤: {e}")