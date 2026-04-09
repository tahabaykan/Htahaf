import pandas as pd, numpy as np

df = pd.read_csv(r'C:\StockTracker\UTALLDATA\F_PRB22exdata.csv')
df['Date'] = pd.to_datetime(df['Date'])
div = 0.39

months = ['2022-05','2022-08','2022-11','2023-02','2023-05','2023-08','2023-11',
          '2024-02','2024-05','2024-08','2024-11','2025-02','2025-05','2025-08','2025-11']

peers = {}
for p in ['PSA PRF','DLR PRJ','BAC PRB','GS PRA','JPM PRC']:
    s = p.replace(' ','_')
    try:
        pdf = pd.read_csv(f'C:\\StockTracker\\UTALLDATA\\{s}22exdata.csv')
        pdf['Date'] = pd.to_datetime(pdf['Date'])
        peers[p] = pdf
    except: pass

out = open(r'C:\StockTracker\quant_engine\fprb_result.txt', 'w')
out.write("F PRB EXDIV DETECTION\n")
out.write(f"Div=${div}, Open-PrevClose, days 10-20\n\n")

for ms in months:
    d10 = pd.Timestamp(f'{ms}-10')
    d20 = pd.Timestamp(f'{ms}-20')
    w = df[(df['Date']>=d10)&(df['Date']<=d20)]
    if len(w)==0:
        out.write(f"{ms}: NODATA\n")
        continue
    
    best_dv = 999
    best_line = ""
    all_lines = []
    for idx in w.index:
        if idx<=0: continue
        r = df.loc[idx]
        pc = df.loc[idx-1,'Close']
        if pc<=0: continue
        og = r['Open']-pc
        ogp = og/pc*100
        pg = []
        for pn,pdf in peers.items():
            pr = pdf[pdf['Date']==r['Date']]
            if len(pr)>0:
                pi=pr.index[0]
                if pi>0:
                    ppc=pdf.loc[pi-1,'Close']
                    if ppc>0: pg.append((pr.iloc[0]['Open']-ppc)/ppc*100)
        pm = np.median(pg) if pg else 0
        dv = ogp - pm
        mk = " <<<" if dv < best_dv else ""
        if dv < best_dv:
            best_dv = dv
        line = f"  {r['Date'].strftime('%m/%d')} O={r['Open']:.2f} PC={pc:.2f} OG={og:+.3f}({ogp:+.1f}%) Peer={pm:+.1f}% Div={dv:+.1f}%"
        all_lines.append((dv, line))
    
    all_lines.sort(key=lambda x: x[0])
    out.write(f"{ms}:\n")
    for i, (dv, line) in enumerate(all_lines):
        mark = " <<<EXDIV" if i==0 and dv < -0.2 else ""
        out.write(f"{line}{mark}\n")
    out.write("\n")

out.close()
print("Done -> fprb_result.txt")
