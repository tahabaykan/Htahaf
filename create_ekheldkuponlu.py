import pandas as pd

tickers = [
    'AEFC','MGR','MGRB','MGRD','ADC PRA','ALL PRI','ALL PRH','AFGB','AFGC','AFGD','AFGE','ACGLO','ACGLN','AIZN','TBB','T PRA','T PRC','AXS PRE','BAC PRM','BAC PRN','BAC PRO','BAC PRP','BAC PRQ','BAC PRS','BAC PRK','COF PRI','COF PRJ','COF PRK','COF PRL','CGABL','CMSA','CMSC','CMSD','CMS PRC','CNO PRA','DLR PRK','DLR PRJ','DLR PRL','DTW','DTG','DTB','DUKB','EAI','ELC','EMP','ENO','EQH PRA','EQH PRC','AGM PRF','AGM PRG','FRT PRC','F PRB','F PRC','GPJA','GL PRD','JPM PRJ','JPM PRK','JPM PRL','JPM PRM','KIM PRL','KIM PRM','KKRS','MET PRE','MET PRF','MS PRL','MS PRO','MS PRK','NRUC','NEE PRN','NTRSO','PRS','PFH','PSA PRF','PSA PRH','PSA PRG','PSA PRI','PSA PRJ','PSA PRK','PSA PRL','PSA PRM','PSA PRN','PSA PRO','PSA PRP','PSA PRQ','PSA PRR','PSA PRS','RF PRE','RNR PRG','RNR PRF','SCHW PRJ','SOJD','SOJC','SOJE','STT PRG','SF PRD','TFC PRR','USB PRP','USB PRQ','USB PRR','USB PRS','WRB PRF','WRB PRE','WRB PRG','WRB PRH','WFC PRA','WFC PRY','WFC PRZ','WFC PRC','WFC PRD'
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

pd.DataFrame(rows, columns=all_columns).to_csv('ekheldkuponlu.csv', index=False)
print('ekheldkuponlu.csv oluşturuldu (veriler öncelikli olarak nalltogether, nnotheldpff, alltogether; bulunamayanlar boş).') 