"""
CGRUP değerlerinin hangi grup dosyalarında olduğunu kontrol eder
"""
import pandas as pd
import os

# Grup dosya eşleşmesi
group_file_map = {
    'heldff': 'ssfinekheldff.csv',
    'helddeznff': 'ssfinekhelddeznff.csv', 
    'heldkuponlu': 'ssfinekheldkuponlu.csv',
    'heldnff': 'ssfinekheldnff.csv',
    'heldflr': 'ssfinekheldflr.csv',
    'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
    'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
    'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
    'heldotelremorta': 'ssfinekheldotelremorta.csv',
    'heldsolidbig': 'ssfinekheldsolidbig.csv',
    'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
    'highmatur': 'ssfinekhighmatur.csv',
    'notcefilliquid': 'ssfineknotcefilliquid.csv',
    'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
    'nottitrekhc': 'ssfineknottitrekhc.csv',
    'salakilliquid': 'ssfineksalakilliquid.csv',
    'shitremhc': 'ssfinekshitremhc.csv'
}

print("=" * 80)
print("CGRUP DEĞERLERİNİN GRUP DOSYALARINDAKİ DAĞILIMI")
print("=" * 80)
print()

# Tüm CGRUP değerlerini topla
all_cgrups = set()
cgrup_by_file = {}

for group, file_name in group_file_map.items():
    if not os.path.exists(file_name):
        print(f"[WARN] {file_name} bulunamadi")
        continue
    
    try:
        df = pd.read_csv(file_name)
        
        if 'CGRUP' not in df.columns:
            print(f"[NO] {file_name}: CGRUP kolonu yok")
            continue
        
        # CGRUP değerlerini al
        cgrups = df['CGRUP'].dropna().unique()
        cgrups = [str(c).strip() for c in cgrups if str(c).strip() != '' and str(c).strip().lower() != 'nan']
        
        if cgrups:
            cgrup_by_file[group] = sorted(cgrups)
            all_cgrups.update(cgrups)
            print(f"[OK] {group:25s} ({file_name:35s}): {len(cgrups):3d} farkli CGRUP")
            print(f"   CGRUP degerleri: {', '.join(cgrups[:10])}")
            if len(cgrups) > 10:
                print(f"   ... ve {len(cgrups) - 10} CGRUP daha")
        else:
            print(f"[--] {group:25s} ({file_name:35s}): CGRUP degeri yok")
    except Exception as e:
        print(f"[ERROR] {file_name} okunamadi: {e}")

print()
print("=" * 80)
print(f"[OZET] Toplam {len(all_cgrups)} farkli CGRUP degeri bulundu")
print("=" * 80)
print()

# CGRUP değerlerine göre hangi dosyalarda olduğunu göster
print("CGRUP DEGERLERINE GORE DAGILIM:")
print("=" * 80)

# CGRUP değerlerini sırala (c400, c425, c450, c475, c500, c525, c550, c600 vb.)
sorted_cgrups = sorted(all_cgrups, key=lambda x: (len(x), x))

for cgrup in sorted_cgrups:
    files_with_cgrup = [group for group, cgrups in cgrup_by_file.items() if cgrup in cgrups]
    if files_with_cgrup:
        print(f"{cgrup:10s} -> {', '.join(files_with_cgrup)}")

print()
print("=" * 80)
print("KUPONLU GRUPLAR (CGRUP iceren):")
print("=" * 80)
kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
for group in kuponlu_groups:
    if group in cgrup_by_file:
        print(f"[OK] {group}: {len(cgrup_by_file[group])} CGRUP degeri")
    else:
        print(f"[NO] {group}: CGRUP degeri yok veya dosya bulunamadi")

