import pandas as pd

tickers = [
    'ABLLL','MITN','MITP','AOMN','AOMD','ATLCZ','CSWCZ','CCIA','CIMN','CIMO','ECCU','ECCW','ECCX','GECCO','GECCZ','GECCI','GECCH','HROWM','HROWL','MFAN','MFAO','MFICL','NYMTI','NYMTG','NEWTI','NEWTG','NEWTH','OCCIM','OXLCN','OXLCL','OXLCI','PDPA','PMTU','PMTV','METCL','METCZ','RWTN','RWTO','RWTP','RWAYL','RWAYZ','SAJ','SAY','SAZ','SPMA','SWKHL','TRINI','TRINZ','TWOD','WHFCL'
]

tickers = list(dict.fromkeys(tickers))  # Tekrarları kaldır

df1 = pd.read_csv('nalltogether.csv', dtype=str)
df2 = pd.read_csv('nnotheldpff.csv', dtype=str)

# Sonuçları burada toplayacağız
rows = []
used = set()

for ticker in tickers:
    row = df1[df1['PREF IBKR'] == ticker]
    if row.empty:
        row = df2[df2['PREF IBKR'] == ticker]
    if not row.empty and ticker not in used:
        rows.append(row.iloc[0])
        used.add(ticker)

if rows:
    result_df = pd.DataFrame(rows)
    result_df.to_csv('ekhighmatur.csv', index=False)
    print('ekhighmatur.csv oluşturuldu.')
else:
    print('Hiçbir ticker bulunamadı, ekhighmatur.csv oluşturulmadı.') 