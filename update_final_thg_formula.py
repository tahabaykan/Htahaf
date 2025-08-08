import re

# Read the original file
with open('ncalculate_final_thg_dynamic.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the old and new formulas
old_formula_pattern = r"""df\.loc\[.*?\]\['FINAL_THG'\] = \(
                            # SMA değişimleri \(0\.3 \+ 0\.3 \+ 0\.4 ağırlık\)
                            \(df\.loc\[.*?\]\['SMA20_chg_norm'\] \* 0\.3 \+ 
                             df\.loc\[.*?\]\['SMA63_chg_norm'\] \* 0\.3 \+ 
                             df\.loc\[.*?\]\['SMA246_chg_norm'\] \* 0\.4\) \+
                            
                            # Normalize değerler grubu \(0\.35 ağırlık\)
                            \(df\.loc\[.*?\]\['6M_High_diff_norm'\] \+ 
                             df\.loc\[.*?\]\['6M_Low_diff_norm'\] \+ 
                             df\.loc\[.*?\]\['3M_High_diff_norm'\] \+ 
                             df\.loc\[.*?\]\['3M_Low_diff_norm'\] \+ 
                             df\.loc\[.*?\]\['1Y_High_diff_norm'\] \+ 
                             df\.loc\[.*?\]\['1Y_Low_diff_norm'\]\) \* 0\.35 \+
                            
                            # Aug4 ve Oct19 değerleri \* 0\.15
                            \(df\.loc\[.*?\]\['Aug4_chg_norm'\] \* 0\.7 \+ 
                             df\.loc\[.*?\]\['Oct19_chg_norm'\] \* 1\.3\) \* 0\.15 \+
                            
                            # Solidity Score \* piyasa koşullarına göre ağırlık
                            df\.loc\[.*?\]\['SOLIDITY_SCORE_NORM'\] \* solidity_weight \+
                            
                            # Normalize edilmiş CUR_YIELD \* piyasa koşullarına göre ağırlık
                            df\.loc\[.*?\]\['CUR_YIELD_NORM'\] \* exp_return_weight
                        \)"""

new_formula_pattern = r"""df.loc[{}]['FINAL_THG'] = (
                            # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) * 3
                            (df.loc[{}]['SMA20_chg_norm'] * 0.3 + 
                             df.loc[{}]['SMA63_chg_norm'] * 0.3 + 
                             df.loc[{}]['SMA246_chg_norm'] * 0.4) * 3 +
                            
                            # Normalize değerler grubu (0.35 ağırlık) * 2
                            (df.loc[{}]['6M_High_diff_norm'] + 
                             df.loc[{}]['6M_Low_diff_norm'] + 
                             df.loc[{}]['3M_High_diff_norm'] + 
                             df.loc[{}]['3M_Low_diff_norm'] + 
                             df.loc[{}]['1Y_High_diff_norm'] + 
                             df.loc[{}]['1Y_Low_diff_norm']) * 0.35 * 2 +
                            
                            # Aug4 ve Oct19 değerleri * 0.15 (değişmedi)
                            (df.loc[{}]['Aug4_chg_norm'] * 0.7 + 
                             df.loc[{}]['Oct19_chg_norm'] * 1.3) * 0.15 +
                            
                            # Solidity Score * 2 (sabit ağırlık)
                            df.loc[{}]['SOLIDITY_SCORE_NORM'] * 2 +
                            
                            # Normalize edilmiş CUR_YIELD * 3 (sabit ağırlık)
                            df.loc[{}]['CUR_YIELD_NORM'] * 3
                        )"""

# Replace all occurrences
def replace_formula(match):
    # Extract the mask part from the original match
    mask_part = re.search(r'df\.loc\[(.*?)\]', match.group(0))
    if mask_part:
        mask = mask_part.group(1)
        return new_formula_pattern.format(mask, mask, mask, mask, mask, mask, mask, mask, mask, mask, mask, mask, mask, mask)
    return match.group(0)

# Apply the replacement
updated_content = re.sub(old_formula_pattern, replace_formula, content, flags=re.MULTILINE | re.DOTALL)

# Also replace the simpler df['FINAL_THG'] patterns
simple_old_pattern = r"""df\['FINAL_THG'\] = \(
                        # SMA değişimleri \(0\.3 \+ 0\.3 \+ 0\.4 ağırlık\)
                        \(df\['SMA20_chg_norm'\] \* 0\.3 \+ 
                         df\['SMA63_chg_norm'\] \* 0\.3 \+ 
                         df\['SMA246_chg_norm'\] \* 0\.4\) \+
                        
                        # Normalize değerler grubu \(0\.35 ağırlık\)
                        \(df\['6M_High_diff_norm'\] \+ 
                         df\['6M_Low_diff_norm'\] \+ 
                         df\['3M_High_diff_norm'\] \+ 
                         df\['3M_Low_diff_norm'\] \+ 
                         df\['1Y_High_diff_norm'\] \+ 
                         df\['1Y_Low_diff_norm'\]\) \* 0\.35 \+
                        
                        # Aug4 ve Oct19 değerleri \* 0\.15
                        \(df\['Aug4_chg_norm'\] \* 0\.7 \+ 
                         df\['Oct19_chg_norm'\] \* 1\.3\) \* 0\.15 \+
                        
                        # Solidity Score \* piyasa koşullarına göre ağırlık
                        df\['SOLIDITY_SCORE_NORM'\] \* solidity_weight \+
                        
                        # Normalize edilmiş CUR_YIELD \* piyasa koşullarına göre ağırlık
                        df\['CUR_YIELD_NORM'\] \* exp_return_weight
                    \)"""

simple_new_pattern = r"""df['FINAL_THG'] = (
                        # SMA değişimleri (0.3 + 0.3 + 0.4 ağırlık) * 3
                        (df['SMA20_chg_norm'] * 0.3 + 
                         df['SMA63_chg_norm'] * 0.3 + 
                         df['SMA246_chg_norm'] * 0.4) * 3 +
                        
                        # Normalize değerler grubu (0.35 ağırlık) * 2
                        (df['6M_High_diff_norm'] + 
                         df['6M_Low_diff_norm'] + 
                         df['3M_High_diff_norm'] + 
                         df['3M_Low_diff_norm'] + 
                         df['1Y_High_diff_norm'] + 
                         df['1Y_Low_diff_norm']) * 0.35 * 2 +
                        
                        # Aug4 ve Oct19 değerleri * 0.15 (değişmedi)
                        (df['Aug4_chg_norm'] * 0.7 + 
                         df['Oct19_chg_norm'] * 1.3) * 0.15 +
                        
                        # Solidity Score * 2 (sabit ağırlık)
                        df['SOLIDITY_SCORE_NORM'] * 2 +
                        
                        # Normalize edilmiş CUR_YIELD * 3 (sabit ağırlık)
                        df['CUR_YIELD_NORM'] * 3
                    )"""

updated_content = re.sub(simple_old_pattern, simple_new_pattern, updated_content, flags=re.MULTILINE | re.DOTALL)

# Write the updated content back to the file
with open('ncalculate_final_thg_dynamic.py', 'w', encoding='utf-8') as f:
    f.write(updated_content)

print("FINAL_THG formülleri başarıyla güncellendi!")
print("\nYeni ağırlıklar:")
print("- SMA değişimleri: × 3")
print("- Normalize değerler: × 2") 
print("- Aug4/Oct19: × 0.15 (değişmedi)")
print("- Solidity Score: × 2 (sabit)")
print("- CUR_YIELD_NORM: × 3 (sabit)") 