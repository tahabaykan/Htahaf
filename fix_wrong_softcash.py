import pandas as pd

# Kullanıcıdan gelen hisse listesi
wrong_tickers = '''ACP PRA
AGM PRE
BCV PRA
BWBBP
CUBB
ECF PRA
EFSCP
ENJ
ETI PR
GAB PRG
GAB PRH
GAB PRK
GDV PRH
GDV PRK
GGN PRB
GGT PRE
GGT PRG
GNT PRA
GRBK PRA
GUT PRC
NCV PRA
NCZ PRA
NYMTZ
OPP PRA
OPP PRB
REXR PRB
REXR PRC
ALTG PRA
AOMN
ATLCP
BANFP
CCIA
CGBDL
CHMI PRA
CHMI PRB
CIMN
CIMO
CMRE PRB
CMRE PRC
CMRE PRD
CSWCZ
CUBI PRF
DSX PRB
DX PRC
ECC PRD
ECCC
ECCF
ECCU
ECCV
ECCW
ECCX
EFC PRD
EICA
EICB
EICC
EIIA
ET PRI
FHN PRC
FRMEP
GAINL
GAM PRB
GECCH
GECCI
GECCO
GECCZ
GLADZ
GMRE PRA
HCXY
HNNAZ
HOVNP
HROWL
HROWM
HTFB
HTFC
INBKZ
METCL
METCZ
MFAO
MFICL
MITN
MITP
MITT PRA
MITT PRB
MITT PRC
NEWTG
NEWTH
NEWTI
NYMTG
NYMTI
OCCIM
OCCIN
OCCIO
OFSSH
OXLCG
OXLCI
OXLCL
OXLCN
OXLCO
OXLCP
OXLCZ
OXSQG
OXSQZ
PDPA
PMTU
PRIF PRD
PRIF PRJ
PRIF PRK
PRIF PRL
RIV PRA
RWAYL
RWAYZ
RWT PRA
RWTN
RWTO
RWTP
SAJ
SAY
SAZ
SB PRC
SB PRD
SPMA
SSSSL
SWKHL
TFINP
TRTN PRA
UCB PRI
WHFCL
XFLT PRA
XOMAO
XOMAP
AOMD
MBNKO'''.splitlines()

# nallsmaff.csv ve nnotheldsmaduz.csv'yi yükle
nallsmaff = pd.read_csv('nallsmaff.csv')
nnotheldsmaduz = pd.read_csv('nnotheldsmaduz.csv')

def get_ticker_col(df):
    for col in df.columns:
        if 'PREF IBKR' in col or 'PREF_IBKR' in col:
            return col
    return None

ticker_col = get_ticker_col(nallsmaff)
duz_col = get_ticker_col(nnotheldsmaduz)

# Ticker'ları temizle
nallsmaff[ticker_col] = nallsmaff[ticker_col].astype(str).str.strip().str.upper()
nnotheldsmaduz[duz_col] = nnotheldsmaduz[duz_col].astype(str).str.strip().str.upper()

# Hangi hisseler taşınacak?
wrong_tickers_upper = [t.strip().upper() for t in wrong_tickers]
keep_in_nallsmaff = {'MITT PRC', 'INBKZ', 'CHMI PRB'}

# Taşınacaklar: wrong_tickers - keep_in_nallsmaff
move_tickers = [t for t in wrong_tickers_upper if t not in keep_in_nallsmaff]

# nallsmaff.csv'den çıkar, nnotheldsmaduz.csv'ye ekle
move_df = nallsmaff[nallsmaff[ticker_col].isin(move_tickers)]
remain_df = nallsmaff[~nallsmaff[ticker_col].isin(move_tickers)]

# Kolonları eşleştir
move_df = move_df.reindex(columns=nnotheldsmaduz.columns, fill_value='')

# nnotheldsmaduz.csv'ye ekle
nnotheldsmaduz = pd.concat([nnotheldsmaduz, move_df], ignore_index=True)

# Kaydet
remain_df.to_csv('nallsmaff.csv', index=False, encoding='utf-8-sig')
nnotheldsmaduz.to_csv('nnotheldsmaduz.csv', index=False, encoding='utf-8-sig')

print(f"Taşınan hisse sayısı: {len(move_df)}")
print(f"nallsmaff.csv kalan: {len(remain_df)}")
print(f"nnotheldsmaduz.csv yeni toplam: {len(nnotheldsmaduz)}") 