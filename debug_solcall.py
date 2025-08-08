import pandas as pd

# FINEK dosyasını oku
df = pd.read_csv('finekheldkuponlu.csv', encoding='utf-8-sig')

# GPJA ve AFGB için detaylı hesaplama
gpja = df[df['PREF IBKR'] == 'GPJA'].iloc[0]
afgb = df[df['PREF IBKR'] == 'AFGB'].iloc[0]

print('=== GPJA HESAPLAMA ===')
print(f'Adj Risk Premium: {gpja["Adj Risk Premium"]}')
print(f'Adj Risk Premium tipi: {type(gpja["Adj Risk Premium"])}')
print(f'Adj Risk Premium * 1000: {gpja["Adj Risk Premium"] * 1000}')
print(f'SOLIDITY_SCORE_NORM: {gpja["SOLIDITY_SCORE_NORM"]}')
print(f'SOLIDITY_SCORE_NORM / 2: {gpja["SOLIDITY_SCORE_NORM"] / 2}')
print(f'Beklenen SOLCALL_SCORE: {(gpja["Adj Risk Premium"] * 1000) + (gpja["SOLIDITY_SCORE_NORM"] / 2)}')
print(f'Gerçek SOLCALL_SCORE: {gpja["SOLCALL_SCORE"]}')

print('\n=== AFGB HESAPLAMA ===')
print(f'Adj Risk Premium: {afgb["Adj Risk Premium"]}')
print(f'Adj Risk Premium tipi: {type(afgb["Adj Risk Premium"])}')
print(f'Adj Risk Premium * 1000: {afgb["Adj Risk Premium"] * 1000}')
print(f'SOLIDITY_SCORE_NORM: {afgb["SOLIDITY_SCORE_NORM"]}')
print(f'SOLIDITY_SCORE_NORM / 2: {afgb["SOLIDITY_SCORE_NORM"] / 2}')
print(f'Beklenen SOLCALL_SCORE: {(afgb["Adj Risk Premium"] * 1000) + (afgb["SOLIDITY_SCORE_NORM"] / 2)}')
print(f'Gerçek SOLCALL_SCORE: {afgb["SOLCALL_SCORE"]}')

print('\n=== TÜM ADJ RISK PREMIUM DEĞERLERİ ===')
adj_risk_values = df['Adj Risk Premium'].dropna()
print(f'Toplam geçerli değer: {len(adj_risk_values)}')
print(f'Min: {adj_risk_values.min()}')
print(f'Max: {adj_risk_values.max()}')
print(f'Örnek değerler: {adj_risk_values.head(10).tolist()}') 