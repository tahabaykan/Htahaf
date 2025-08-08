import pandas as pd

def show_total_score_norms(top_n=30):
    df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
    sorted_df = df.sort_values('TOTAL_SCORE_NORM', ascending=False)
    print(f"\n{'SIRA':<4} | {'CMON':<8} | {'PREF IBKR':<12} | {'TOTAL_SCORE_NORM':<18}")
    print('-'*50)
    for idx in range(top_n):
        row = sorted_df.iloc[idx]
        print(f"{idx+1:<4} | {row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['TOTAL_SCORE_NORM']:<18.2f}")
    print(f"\nToplam hisse sayısı: {len(df)}")
    print(f"En yüksek TOTAL_SCORE_NORM: {sorted_df['TOTAL_SCORE_NORM'].max():.2f}")
    print(f"En düşük TOTAL_SCORE_NORM: {sorted_df['TOTAL_SCORE_NORM'].min():.2f}")

if __name__ == "__main__":
    show_total_score_norms(30) 