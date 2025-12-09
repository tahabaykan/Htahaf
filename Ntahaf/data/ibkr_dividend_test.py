from ib_insync import *

# IB bağlantısı
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=1)

# Hisse sözleşmesi
contract = Stock('AFGE', 'SMART', 'USD')

# Temel verileri al
fundamental_data = ib.reqFundamentalData(contract, 'ReportsFinSummary')

# Veriyi incele
if fundamental_data:
    print("Temel Veriler (XML):", fundamental_data)
    # XML içinde "Dividend" veya "ExDate" gibi anahtar kelimeleri arayın
    if "Dividend" in fundamental_data:
        print("Temettü bilgisi bulundu!")
    else:
        print("Temettü bilgisi XML'de mevcut değil.")

# Bağlantıyı kapat
ib.disconnect()

