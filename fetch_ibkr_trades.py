from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.execution import ExecutionFilter
import pandas as pd
import time
from datetime import datetime, timedelta
from dateutil import parser

class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.executions = []
        self.done = False

    def error(self, reqId, errorCode, errorString):
        print(f"Error: {reqId}, {errorCode}, {errorString}")

    def execDetails(self, reqId, contract, execution):
        print('DEBUG FILL:', execution.__dict__)
        exec_time = execution.time
        try:
            fill_time = parser.parse(exec_time)
        except Exception:
            fill_time = None
        trade = {
            "Time": fill_time,
            "Fin Instrument": contract.symbol,
            "Action": execution.side,
            "Quantity": execution.shares,
            "Price": execution.price
        }
        self.executions.append(trade)

    def execDetailsEnd(self, reqId):
        print("Tüm işlemler alındı.")
        self.done = True

if __name__ == "__main__":
    app = IBApp()
    app.connect("127.0.0.1", 7496, clientId=42)
    print("Bağlantı kuruldu.")

    # Son 3 gün için başlangıç tarihi
    now = datetime.now()
    start_date = (now - timedelta(days=2)).strftime("%Y%m%d")
    exec_filter = ExecutionFilter()
    exec_filter.time = start_date

    app.reqExecutions(1001, exec_filter)
    # Fillerin gelmesini bekle (maksimum 10 saniye)
    for _ in range(20):
        if app.done:
            break
        time.sleep(0.5)
    app.disconnect()

    # Son 3 gün için Python tarafında da filtrele
    filtered = []
    for trade in app.executions:
        fill_time = trade.get('Time')
        if fill_time and (now - fill_time).days < 3:
            filtered.append(trade)
    df = pd.DataFrame(filtered)
    outname = f"trades_{now.strftime('%Y%m%d')}.csv"
    df.to_csv(outname, index=False)
    print(f"{len(filtered)} işlem {outname} dosyasına kaydedildi.") 