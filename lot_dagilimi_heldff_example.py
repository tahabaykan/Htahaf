import numpy as np
import pandas as pd

def lot_dagilimi(final_thg_list, total_lot=10000, alpha=2, min_lot_thresh=50):
    """
    HELDFF grubu için lot dağılımı hesaplama
    
    Parameters:
    - final_thg_list: FINAL THG skorları listesi
    - total_lot: Toplam dağıtılacak lot miktarı
    - alpha: Güçlendirme faktörü (varsayılan: 2)
    - min_lot_thresh: Minimum lot eşiği (varsayılan: 50)
    
    Returns:
    - Lot dağılımı array'i
    """
    final_thg_arr = np.array(final_thg_list, dtype=np.float64)
    max_score = final_thg_arr.max()
    
    print(f"=== LOT DAĞILIMI HESAPLAMA ===")
    print(f"Toplam lot: {total_lot:,}")
    print(f"Alpha değeri: {alpha}")
    print(f"Minimum lot eşiği: {min_lot_thresh}")
    print(f"En yüksek FINAL THG: {max_score:.2f}")
    print()
    
    # Oranları hesapla ve farkları güçlendir
    relative_scores = (final_thg_arr / max_score) ** alpha
    print("=== GÖRELİ SKORLAR (alpha={}) ===".format(alpha))
    for i, (score, rel_score) in enumerate(zip(final_thg_arr, relative_scores)):
        print(f"Hisse {i+1}: FINAL_THG={score:.2f} → Göreli skor={rel_score:.4f}")
    
    # Lotları ölçekle
    raw_lot_alloc = relative_scores / relative_scores.sum() * total_lot
    print(f"\n=== HAM LOT DAĞILIMI ===")
    for i, (score, raw_lot) in enumerate(zip(final_thg_arr, raw_lot_alloc)):
        print(f"Hisse {i+1}: {raw_lot:.2f} lot")
    
    # Minimum eşik altındakileri sıfırla
    raw_lot_alloc[raw_lot_alloc < min_lot_thresh] = 0
    print(f"\n=== MİNİMUM EŞİK ({min_lot_thresh}) UYGULANDI ===")
    for i, (score, raw_lot) in enumerate(zip(final_thg_arr, raw_lot_alloc)):
        status = "✓" if raw_lot >= min_lot_thresh else "✗ (eşik altı)"
        print(f"Hisse {i+1}: {raw_lot:.2f} lot {status}")
    
    # Kalan lotları tekrar eşit oranda dağıt
    lot_alloc = np.floor(raw_lot_alloc)
    remainder = total_lot - lot_alloc.sum()
    
    print(f"\n=== TAM SAYI LOT DAĞILIMI ===")
    print(f"Toplam dağıtılan: {lot_alloc.sum():,} lot")
    print(f"Kalan lot: {remainder:,}")
    
    # Kalan lotları en yüksek puanlılar arasında dağıtalım
    if remainder > 0:
        sorted_indices = np.argsort(-relative_scores)
        print(f"\n=== KALAN LOT DAĞILIMI (en yüksek skorlulara) ===")
        for i in range(int(remainder)):
            lot_alloc[sorted_indices[i % len(lot_alloc)]] += 1
            print(f"Kalan lot {i+1}: Hisse {sorted_indices[i % len(lot_alloc)]+1}'e +1 lot")
    
    final_lots = lot_alloc.astype(int)
    
    print(f"\n=== SON LOT DAĞILIMI ===")
    total_allocated = final_lots.sum()
    print(f"Toplam dağıtılan lot: {total_allocated:,}")
    print(f"Verimlilik: {(total_allocated/total_lot)*100:.1f}%")
    
    for i, (score, lots) in enumerate(zip(final_thg_arr, final_lots)):
        percentage = (lots / total_lot) * 100 if total_lot > 0 else 0
        print(f"Hisse {i+1}: FINAL_THG={score:.2f} → {lots:,} lot ({percentage:.1f}%)")
    
    return final_lots

def heldff_final_thg_example():
    """
    HELDFF grubu için gerçekçi FINAL THG değerleri ile örnek
    """
    print("=" * 80)
    print("HELDFF GRUBU LOT DAĞILIMI ÖRNEĞİ")
    print("=" * 80)
    print()
    
    # HELDFF formülü: (Solidity score norm × 1) + (Exp ann return norm × 12)
    # Gerçekçi değerler:
    # - Solidity score norm: 5-95 arası
    # - Exp ann return norm: 5-95 arası
    # - FINAL THG: 17-1207 arası
    
    print("HELDFF FINAL THG Formülü:")
    print("(Solidity score norm × 1) + (Exp ann return norm × 12)")
    print()
    
    # Senaryo 1: Normal HELDFF grubu (4 hisse)
    print("=== SENARYO 1: Normal HELDFF Grubu ===")
    print("Hisse 1: Solidity=85, ExpReturn=90 → FINAL_THG = 85×1 + 90×12 = 1,165")
    print("Hisse 2: Solidity=75, ExpReturn=85 → FINAL_THG = 75×1 + 85×12 = 1,095")
    print("Hisse 3: Solidity=65, ExpReturn=80 → FINAL_THG = 65×1 + 80×12 = 1,025")
    print("Hisse 4: Solidity=55, ExpReturn=75 → FINAL_THG = 55×1 + 75×12 = 955")
    print()
    
    senaryo1 = [1165, 1095, 1025, 955]
    print("Senaryo 1 Lot Dağılımı:")
    lot_dagilimi(senaryo1, total_lot=10000, alpha=2, min_lot_thresh=50)
    
    print("\n" + "="*80 + "\n")
    
    # Senaryo 2: Daha geniş HELDFF grubu (6 hisse)
    print("=== SENARYO 2: Geniş HELDFF Grubu ===")
    print("Hisse 1: Solidity=95, ExpReturn=95 → FINAL_THG = 95×1 + 95×12 = 1,235")
    print("Hisse 2: Solidity=90, ExpReturn=90 → FINAL_THG = 90×1 + 90×12 = 1,170")
    print("Hisse 3: Solidity=80, ExpReturn=85 → FINAL_THG = 80×1 + 85×12 = 1,100")
    print("Hisse 4: Solidity=70, ExpReturn=80 → FINAL_THG = 70×1 + 80×12 = 1,030")
    print("Hisse 5: Solidity=60, ExpReturn=75 → FINAL_THG = 60×1 + 75×12 = 960")
    print("Hisse 6: Solidity=50, ExpReturn=70 → FINAL_THG = 50×1 + 70×12 = 890")
    print()
    
    senaryo2 = [1235, 1170, 1100, 1030, 960, 890]
    print("Senaryo 2 Lot Dağılımı:")
    lot_dagilimi(senaryo2, total_lot=15000, alpha=2, min_lot_thresh=100)
    
    print("\n" + "="*80 + "\n")
    
    # Senaryo 3: Farklı alpha değerleri ile karşılaştırma
    print("=== SENARYO 3: Alpha Değerleri Karşılaştırması ===")
    print("Alpha=1: Doğrusal dağılım")
    print("Alpha=2: Karesel dağılım (varsayılan)")
    print("Alpha=3: Küpsel dağılım (daha agresif)")
    print()
    
    senaryo3 = [1200, 1100, 1000, 900, 800]
    
    for alpha in [1, 2, 3]:
        print(f"Alpha={alpha} için lot dağılımı:")
        lot_dagilimi(senaryo3, total_lot=10000, alpha=alpha, min_lot_thresh=50)
        print()

def analyze_formula_impact():
    """
    Formül parametrelerinin etkisini analiz et
    """
    print("=" * 80)
    print("FORMÜL PARAMETRE ANALİZİ")
    print("=" * 80)
    print()
    
    # Test verisi
    test_scores = [1000, 950, 900, 850, 800]
    
    print("Test FINAL THG değerleri:", test_scores)
    print()
    
    # Farklı alpha değerleri
    print("=== ALPHA ETKİSİ ===")
    for alpha in [1, 1.5, 2, 2.5, 3]:
        relative_scores = (np.array(test_scores) / max(test_scores)) ** alpha
        print(f"Alpha={alpha}: {relative_scores}")
    
    print()
    
    # Farklı minimum eşik değerleri
    print("=== MİNİMUM EŞİK ETKİSİ ===")
    for threshold in [0, 50, 100, 200]:
        result = lot_dagilimi(test_scores, total_lot=10000, alpha=2, min_lot_thresh=threshold)
        print(f"Eşik={threshold}: Toplam dağıtılan={result.sum()}, Verimlilik={(result.sum()/10000)*100:.1f}%")

if __name__ == "__main__":
    # Ana örnekleri çalıştır
    heldff_final_thg_example()
    
    # Formül analizi
    analyze_formula_impact()
    
    print("\n" + "="*80)
    print("ÖZET:")
    print("- Alpha=2 ile en yüksek skorlu hisseler daha fazla lot alır")
    print("- Minimum eşik altındaki hisseler lot alamaz")
    print("- Kalan lotlar en yüksek skorlu hisselere dağıtılır")
    print("- Toplam lot verimliliği minimum eşik değerine bağlıdır")
    print("="*80)
