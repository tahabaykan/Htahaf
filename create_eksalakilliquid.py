import pandas as pd

tickers = [
    'BWBBP','CTO PRA','EFC PRD','EFSCP','FGBIP','GOODN','GOODO','LANDO','LANDP','GMRE PRA','GRBK PRA','HOVNP','LBRDP','LFT PRA','MHNC','MHLA','MNSBP','NHPAP','NHPBP','NREF PRA','PRIF PRK','HFRO PRA'
]

# Öncelik sırası: nalltogether.csv > nnotheldpff.csv > alltogether.csv
df1 = pd.read_csv('nalltogether.csv', dtype=str)
df2 = pd.read_csv('nnotheldpff.csv', dtype=str)
df3 = pd.read_csv('alltogether.csv', dtype=str)

all_columns = list(df1.columns)
rows = []

for ticker in tickers:
    row = df1[df1['PREF IBKR'] == ticker]
    if not row.empty:
        rows.append(row.iloc[0].to_dict())
        continue
    row2 = df2[df2['PREF IBKR'] == ticker]
    if not row2.empty:
        rows.append(row2.iloc[0].to_dict())
        continue
    row3 = df3[df3['PREF IBKR'] == ticker]
    if not row3.empty:
        rows.append(row3.iloc[0].to_dict())
        continue
    # Hiçbirinde yoksa sadece PREF IBKR dolu
    empty_row = {col: '' for col in all_columns}
    empty_row['PREF IBKR'] = ticker
    rows.append(empty_row)

pd.DataFrame(rows, columns=all_columns).to_csv('eksalakilliquid.csv', index=False)
print('eksalakilliquid.csv oluşturuldu (veriler öncelikli olarak nalltogether, nnotheldpff, alltogether; bulunamayanlar boş).') 