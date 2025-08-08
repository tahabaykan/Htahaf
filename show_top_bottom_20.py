import pandas as pd

# Load the data
df = pd.read_csv('allcomek_sld.csv')

# Group by CMON and calculate averages
cmon_stats = df.groupby('CMON').agg({
    'PREF IBKR': 'first',
    'COM_MKTCAP': 'mean',
    'MKTCAP_NORM': 'mean',
    'SOLIDITY_SCORE': 'mean',
    'SOLIDITY_SCORE_NORM': 'mean'
}).reset_index()

print("=== EN GÜÇLÜ 20 CMON STOCK ===")
print("="*60)
top_20 = cmon_stats.nlargest(20, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
for idx, row in top_20.iterrows():
    print(f"{row['CMON']:>6} ({row['PREF IBKR']:>10}): {row['SOLIDITY_SCORE']:>8.2f} | {row['SOLIDITY_SCORE_NORM']:>6.2f}")

print("\n" + "="*60)
print("=== EN ZAYIF 20 CMON STOCK ===")
print("="*60)
bottom_20 = cmon_stats.nsmallest(20, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
for idx, row in bottom_20.iterrows():
    print(f"{row['CMON']:>6} ({row['PREF IBKR']:>10}): {row['SOLIDITY_SCORE']:>8.2f} | {row['SOLIDITY_SCORE_NORM']:>6.2f}")

print("\n" + "="*60)
print("ANALİZ TAMAMLANDI")
print("="*60) 