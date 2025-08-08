import pandas as pd

# Load the data
df = pd.read_csv('finekheldkuponlu.csv')

# Sort by FINAL_THG in descending order for top 10
top_10 = df.nlargest(10, 'FINAL_THG')[['PREF IBKR', 'CMON', 'FINAL_THG', 'EXP_ANN_RETURN', 'YTM', 'YTC', 'SOLIDITY_SCORE_NORM']]

# Sort by FINAL_THG in ascending order for bottom 10
bottom_10 = df.nsmallest(10, 'FINAL_THG')[['PREF IBKR', 'CMON', 'FINAL_THG', 'EXP_ANN_RETURN', 'YTM', 'YTC', 'SOLIDITY_SCORE_NORM']]

print("=== TOP 10 FINAL_THG STOCKS ===")
print(top_10.to_string(index=False))
print("\n")

print("=== BOTTOM 10 FINAL_THG STOCKS ===")
print(bottom_10.to_string(index=False))

# Save to CSV files
top_10.to_csv('top_10_final_thg_kuponlu.csv', index=False)
bottom_10.to_csv('bottom_10_final_thg_kuponlu.csv', index=False)

print(f"\nTop 10 saved to: top_10_final_thg_kuponlu.csv")
print(f"Bottom 10 saved to: bottom_10_final_thg_kuponlu.csv") 