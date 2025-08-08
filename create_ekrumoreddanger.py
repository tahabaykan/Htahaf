import pandas as pd

tickers = [
    'BHFAL','BHFAP','BHFAO','BHFAN','BHFAM','DBRG PRJ','DBRG PRI','DBRG PRH','MSBIP','SCE PRG','SCE PRL','SCE PRK','SCE PRJ','SCE PRH','SCE PRM','SCE PRN','UZE','UZD','UZF'
]

df = pd.read_csv('alltogether.csv', dtype=str)
all_columns = list(df.columns)
rows = []

for ticker in tickers:
    row = df[df['PREF IBKR'] == ticker]
    if not row.empty:
        rows.append(row.iloc[0].to_dict())
    else:
        empty_row = {col: '' for col in all_columns}
        empty_row['PREF IBKR'] = ticker
        rows.append(empty_row)

pd.DataFrame(rows, columns=all_columns).to_csv('ekrumoreddanger.csv', index=False)
print('ekrumoreddanger.csv oluşturuldu (veriler sadece alltogether.csv den çekildi, bulunamayanlar boş).') 