import pandas as pd

tickers = [
    'ACP PRA','BCV PRA','ECC PRD','ECF PRA','ENJ','ETI PR','AGM PRD','AGM PRE','GDV PRH','GDV PRK','GAB PRH','GAB PRG','GAB PRK','GGT PRE','GGT PRG','GUT PRC','GGN PRB','GNT PRA','OPP PRA','OPP PRB','NCV PRA','NCZ PRA'
]

df1 = pd.read_csv('nalltogether.csv', dtype=str)
df2 = pd.read_csv('nnotheldpff.csv', dtype=str)

rows_held = []
rows_notheld = []
used = set()

for ticker in tickers:
    if ticker in used:
        continue
    row = df1[df1['PREF IBKR'] == ticker]
    if not row.empty:
        rows_held.append(row.iloc[0])
        used.add(ticker)
    else:
        row2 = df2[df2['PREF IBKR'] == ticker]
        if not row2.empty:
            rows_notheld.append(row2.iloc[0])
            used.add(ticker)

if rows_held:
    pd.DataFrame(rows_held).to_csv('ekcefilliquid.csv', index=False)
    print('ekcefilliquid.csv oluşturuldu.')
else:
    print('ekcefilliquid.csv için uygun ticker bulunamadı.')

if rows_notheld:
    pd.DataFrame(rows_notheld).to_csv('eknotcefilliquid.csv', index=False)
    print('eknotcefilliquid.csv oluşturuldu.')
else:
    print('eknotcefilliquid.csv için uygun ticker bulunamadı.') 