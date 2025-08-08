import pandas as pd

# CSV dosyasını oku
df = pd.read_csv('sldekheldkuponlu.csv')

# Market cap sütununu sayısal hale getir
df['COM_MKTCAP'] = pd.to_numeric(df['COM_MKTCAP'], errors='coerce')

# Market cap'e göre sırala (en yüksekten en düşüğe)
df_sorted = df.sort_values('COM_MKTCAP', ascending=False)

print("=== EN YÜKSEK MARKET CAP'Lİ ŞİRKETLER ===")
print(f"Toplam şirket sayısı: {len(df)}")
print("\nEn yüksek 20 market cap:")
print(df_sorted[['PREF IBKR', 'CMON', 'COM_MKTCAP', 'SOLIDITY_SCORE']].head(20))

print("\n=== MARKET CAP ARALIKLARI ===")
print(f"En yüksek market cap: {df_sorted['COM_MKTCAP'].max():.2f}")
print(f"En düşük market cap: {df_sorted['COM_MKTCAP'].min():.2f}")
print(f"Ortalama market cap: {df_sorted['COM_MKTCAP'].mean():.2f}")
print(f"Medyan market cap: {df_sorted['COM_MKTCAP'].median():.2f}")

# Market cap aralıklarını göster
print("\n=== MARKET CAP DAĞILIMI ===")
bins = [0, 10, 50, 100, 500, 1000, float('inf')]
labels = ['0-10B', '10-50B', '50-100B', '100-500B', '500B-1T', '1T+']
df_sorted['MKTCAP_RANGE'] = pd.cut(df_sorted['COM_MKTCAP'], bins=bins, labels=labels, right=False)
print(df_sorted['MKTCAP_RANGE'].value_counts().sort_index()) 