import numpy as np
import pandas as pd

def lot_dagilimi_top5(final_thg_list, total_lot=10000, alpha=2, min_lot_thresh=100):
    """
    Herhangi bir grup için TOP 5 hisse arasında lot dağılımı hesaplama
    Lot sayıları 100'lük sayılara yuvarlanır
    
    Parameters:
    - final_thg_list: FINAL THG skorları listesi (sadece TOP 5)
    - total_lot: Toplam dağıtılacak lot miktarı
    - alpha: Güçlendirme faktörü (varsayılan: 2)
    - min_lot_thresh: Minimum lot eşiği (varsayılan: 100)
    
    Returns:
    - Lot dağılımı array'i (100'lük sayılara yuvarlanmış)
    """
    final_thg_arr = np.array(final_thg_list, dtype=np.float64)
    max_score = final_thg_arr.max()
    
    print(f"=== TOP 5 HİSE LOT DAĞILIMI HESAPLAMA ===")
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
    
    # Lotları 100'lük sayılara yuvarla
    lot_alloc = np.round(raw_lot_alloc / 100) * 100
    lot_alloc = lot_alloc.astype(int)
    
    print(f"\n=== 100'LÜK SAYILARA YUVARLANMIŞ LOT DAĞILIMI ===")
    for i, (score, lots) in enumerate(zip(final_thg_arr, lot_alloc)):
        print(f"Hisse {i+1}: {lots:,} lot")
    
    # Toplam dağıtılan lotu kontrol et
    total_allocated = lot_alloc.sum()
    print(f"\nToplam dağıtılan lot: {total_allocated:,}")
    print(f"Verimlilik: {(total_allocated/total_lot)*100:.1f}%")
    
    # Eğer toplam lot farkı varsa, en yüksek skorlu hisseye ekle
    if total_allocated != total_lot:
        difference = total_lot - total_allocated
        print(f"\nLot farkı: {difference:,}")
        
        if difference > 0:
            # En yüksek skorlu hisseye ekle
            max_idx = np.argmax(relative_scores)
            lot_alloc[max_idx] += difference
            print(f"Fark {difference:,} lot en yüksek skorlu Hisse {max_idx+1}'e eklendi")
        else:
            # En yüksek skorlu hisseden çıkar
            max_idx = np.argmax(relative_scores)
            lot_alloc[max_idx] += difference  # difference negatif olduğu için çıkarır
            print(f"Fark {abs(difference):,} lot en yüksek skorlu Hisse {max_idx+1}'den çıkarıldı")
    
    print(f"\n=== SON LOT DAĞILIMI (100'lük yuvarlanmış) ===")
    final_total = lot_alloc.sum()
    print(f"Toplam dağıtılan lot: {final_total:,}")
    print(f"Verimlilik: {(final_total/total_lot)*100:.1f}%")
    
    for i, (score, lots) in enumerate(zip(final_thg_arr, lot_alloc)):
        percentage = (lots / total_lot) * 100 if total_lot > 0 else 0
        print(f"Hisse {i+1}: FINAL_THG={score:.2f} → {lots:,} lot ({percentage:.1f}%)")
    
    return lot_alloc

def grup_analizi(grup_adi, dosya_adi, total_lot=10000):
    """
    Belirli bir grup için TOP 5 hisse analizi yap
    """
    print("=" * 100)
    print(f"{grup_adi.upper()} GRUBU - TOP 5 HİSE LOT DAĞILIMI ANALİZİ")
    print("=" * 100)
    print()
    
    try:
        # Grup verilerini oku
        df = pd.read_csv(dosya_adi, encoding='utf-8-sig')
        print(f"{grup_adi} grubunda toplam {len(df)} hisse bulundu")
        print()
        
        # FINAL THG değerlerini al
        final_thg_values = df['FINAL_THG'].dropna().values
        print(f"FINAL THG değerleri bulunan hisse sayısı: {len(final_thg_values)}")
        
        if len(final_thg_values) == 0:
            print(f"{grup_adi} için FINAL THG değeri bulunamadı!")
            return
        
        # TOP 5 hisseyi bul
        top_5_indices = np.argsort(final_thg_values)[-5:][::-1]
        top_5_values = final_thg_values[top_5_indices]
        top_5_symbols = [df.iloc[idx]['PREF IBKR'] if 'PREF IBKR' in df.columns else f"Hisse_{idx+1}" for idx in top_5_indices]
        
        print(f"\n=== TOP 5 FINAL THG HİSELERİ ===")
        for i, (symbol, value) in enumerate(zip(top_5_symbols, top_5_values)):
            print(f"{i+1}. {symbol}: {value:.2f}")
        
        print(f"\n=== TOP 5 İSTATİSTİKLERİ ===")
        print(f"En yüksek FINAL THG: {top_5_values.max():.2f}")
        print(f"En düşük FINAL THG: {top_5_values.min():.2f}")
        print(f"Ortalama FINAL THG: {top_5_values.mean():.2f}")
        print(f"Standart sapma: {top_5_values.std():.2f}")
        
        print("\n" + "="*100 + "\n")
        
        # Senaryo 1: Alpha=3, min_lot_thresh=100 (varsayılan - artırıldı)
        print("=== SENARYO 1: Alpha=3, Min Lot Eşiği=100 (Varsayılan - Artırıldı) ===")
        lot_dagilimi_top5(top_5_values, total_lot=total_lot, alpha=3, min_lot_thresh=100)
        
        print("\n" + "="*100 + "\n")
        
        # Senaryo 2: Alpha=4, min_lot_thresh=100 (daha hassas)
        print("=== SENARYO 2: Alpha=4, Min Lot Eşiği=100 (Daha Hassas) ===")
        lot_dagilimi_top5(top_5_values, total_lot=total_lot, alpha=4, min_lot_thresh=100)
        
        print("\n" + "="*100 + "\n")
        
        # Senaryo 3: Alpha=5, min_lot_thresh=100 (çok hassas - artırıldı)
        print("=== SENARYO 3: Alpha=5, Min Lot Eşiği=100 (Çok Hassas - Artırıldı) ===")
        lot_dagilimi_top5(top_5_values, total_lot=total_lot, alpha=5, min_lot_thresh=100)
        
        print("\n" + "="*100)
        print(f"{grup_adi.upper()} GRUBU ÖZET:")
        print(f"- Sadece TOP 5 hisse arasında lot dağılımı yapıldı")
        print(f"- Lot sayıları 100'lük sayılara yuvarlandı")
        print(f"- Alpha=3: Varsayılan hassasiyet (artırıldı)")
        print(f"- Alpha=4: Daha hassas dağılım")
        print(f"- Alpha=5: Çok hassas dağılım (artırıldı)")
        print("="*100)
        
    except Exception as e:
        print(f"{grup_adi} grubu için hata oluştu: {e}")
        print("Dosya okunamadı veya FINAL THG kolonu bulunamadı.")

def tum_gruplar_analizi():
    """
    Tüm gruplar için analiz yap
    """
    print("=" * 120)
    print("TÜM GRUPLAR İÇİN TOP 5 HİSE LOT DAĞILIMI ANALİZİ")
    print("=" * 120)
    print()
    
    # Grup listesi
    gruplar = [
        ("HELDFF", "ssfinekheldff.csv", 10000),
        ("DEZNFF", "ssfinekhelddeznff.csv", 10000),
        ("HELDKUPONLU", "ssfinekheldkuponlu.csv", 10000)
    ]
    
    for grup_adi, dosya_adi, total_lot in gruplar:
        try:
            grup_analizi(grup_adi, dosya_adi, total_lot)
            print("\n" + "="*120 + "\n")
        except Exception as e:
            print(f"{grup_adi} grubu analiz edilemedi: {e}")
            print("\n" + "="*120 + "\n")
    
    print("TÜM GRUPLAR ANALİZİ TAMAMLANDI!")
    print("="*120)

if __name__ == "__main__":
    tum_gruplar_analizi()
