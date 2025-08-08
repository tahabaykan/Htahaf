import pandas as pd

tickers = [
    'CUBB','EICA','ECCC','FCRX','GAINN','GAINZ','LANDM','HNNAZ','HTFB','HTFC','NMFCZ','NEWTZ','OFSSH','OCCIO','OCCIN','OXLCP','OXLCO','OXLCZ','OXSQZ','PXFNZ','PRIF PRD','PRIF PRJ','PRIF PRL','SAT','SSSSL','TVE','TVC','XFLT PRA','GAM PRB','BPOPM','ATLCL'
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
    pd.DataFrame(rows_held).to_csv('ekheldbesmaturlu.csv', index=False)
    print('ekheldbesmaturlu.csv oluşturuldu.')
else:
    print('ekheldbesmaturlu.csv için uygun ticker bulunamadı.')

if rows_notheld:
    pd.DataFrame(rows_notheld).to_csv('eknotbesmaturlu.csv', index=False)
    print('eknotbesmaturlu.csv oluşturuldu.')
else:
    print('eknotbesmaturlu.csv için uygun ticker bulunamadı.') 