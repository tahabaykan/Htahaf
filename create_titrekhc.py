import pandas as pd

tickers = [
    'ACR PRC','MITT PRC','ALTG PRA','GSL PRB','CHMI PRB','CMRE PRC','CMRE PRD','CMRE PRB','CUBI PRF','DSX PRB','INBKZ','MFA PRC','NYMTM','FRMEP','RWT PRA','RPT PRC','RLJ PRA','SB PRC','SB PRD','SEAL PRA','SEAL PRB','TRTN PRA','TRTN PRB','XOMAO','XOMAP','BANFP'
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
        rows_held.append(row.iloc[0].to_dict())
        used.add(ticker)
    else:
        row2 = df2[df2['PREF IBKR'] == ticker]
        if not row2.empty:
            rows_notheld.append(row2.iloc[0].to_dict())
            used.add(ticker)

if rows_held:
    pd.DataFrame(rows_held, columns=df1.columns).to_csv('ekheldtitrekhc.csv', index=False)
    print('ekheldtitrekhc.csv oluşturuldu.')
else:
    print('ekheldtitrekhc.csv için uygun ticker bulunamadı.')

if rows_notheld:
    pd.DataFrame(rows_notheld, columns=df2.columns).to_csv('eknottitrekhc.csv', index=False)
    print('eknottitrekhc.csv oluşturuldu.')
else:
    print('eknottitrekhc.csv için uygun ticker bulunamadı.') 