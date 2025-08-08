import pandas as pd
import re

def clean_ticker(ticker):
    if pd.isna(ticker):
        return ticker
    if ticker == "-":
        return "PR pr"
    if ticker == "WRB-F":
        return "WRB PRF"
    # ACP-A -> ACP PRA, XYZ-B -> XYZ PRB
    m = re.match(r"^([A-Za-z0-9]+)-([A-Za-z])$", str(ticker))
    if m:
        return f"{m.group(1)} PR{m.group(2)}"
    return ticker

def format_date(val):
    if pd.isna(val):
        return ''
    try:
        dt = pd.to_datetime(val)
        return dt.strftime('%m/%d/%Y')
    except Exception:
        return str(val).split()[0]  # fallback: just date part

# Dosyayı oku
df = pd.read_excel("forcursor.xlsx")

# Kolon adlarını temizle (küçük harf, boşlukları ve satır sonlarını kaldır)
def clean_col(col):
    return str(col).strip().replace('\n', '').replace('  ', ' ').replace(' ', '').lower()

cleaned_cols = {clean_col(col): col for col in df.columns}

# İstenen başlıkların temiz halleri
wanted = {
    'qdi': 'QDI',
    'sector': 'Sector',
    'fix/float': 'Fix/Float',
    'type': 'Type',
    'ticker': 'PREF IBKR',
    'couponpercent': 'Coupon percent',
    'currentprice': 'Current price',
    'ig': 'IG',
    'quarterlyint/div': 'Quarterly Int / Div',
    '1stcall': '1st Call',
    'maturitydate': 'Maturity Date'
}

# Gerçek kolon adlarını bul
col_map = {}
for want_clean, out_name in wanted.items():
    for cleaned, real in cleaned_cols.items():
        if want_clean == cleaned:
            col_map[real] = out_name
            break

# Sadece bulunan kolonları al
selected = df[list(col_map.keys())].copy()

# Ticker kolonunu düzenle
if 'Ticker' in selected.columns:
    selected['PREF IBKR'] = selected['Ticker'].apply(clean_ticker)
    selected = selected.drop(columns=['Ticker'])

# Current price'da 'Redeem' olanları çıkar
cp_col = [c for c in selected.columns if 'Current' in c and 'Price' in c]
if cp_col:
    selected = selected[selected[cp_col[0]].astype(str).str.lower() != 'redeem']

# Tarih kolonlarını formatla
for date_col in ['1st Call', 'Maturity Date']:
    if date_col in selected.columns:
        selected[date_col] = selected[date_col].apply(format_date)

# Kolon sırasını ayarla
final_columns = [
    'QDI','Sector','Fix/Float','Type','PREF IBKR','Coupon percent','Current price','IG','Quarterly Int / Div','1st Call','Maturity Date'
]
# Sadece mevcut olanları al
final_columns = [c for c in final_columns if c in selected.columns]
selected = selected[final_columns]

# Sonucu kaydet
selected.to_csv('ekcurdata.csv', index=False)
print('ekcurdata.csv olusturuldu.') 