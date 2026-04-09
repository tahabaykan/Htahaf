import sys, json
sys.path.insert(0, '.')
from app.core.redis_client import get_redis_client

r = get_redis_client()

# HAMPRO befday
bef = r.get('psfalgo:befday:positions:HAMPRO')
bef_date = r.get('psfalgo:befday:date:HAMPRO')
print(f"HAMPRO Befday key: {'EXISTS ('+str(len(json.loads(bef.decode() if isinstance(bef, bytes) else bef)))+' entries)' if bef else 'NONE'}")
print(f"HAMPRO Befday date: {bef_date.decode() if bef_date and isinstance(bef_date, bytes) else bef_date if bef_date else 'NONE'}")

# RevnBookCheck state
rev_state = r.get('psfalgo:revnbookcheck:state')
if rev_state:
    rs = json.loads(rev_state.decode() if isinstance(rev_state, bytes) else rev_state)
    print(f"RevnBookCheck: account={rs.get('account_mode')}, running={rs.get('running')}")
else:
    print("No RevnBookCheck state key")

# Dual process
dp = r.get('psfalgo:dual_process:state')
if dp:
    dps = json.loads(dp.decode() if isinstance(dp, bytes) else dp)
    print(f"Dual Process: running={dps.get('running')}, phase={dps.get('current_phase')}, accounts={dps.get('accounts')}")
else:
    print("No dual process state")

# Check IBKR_PED specific - MET PRF
pos = r.get('psfalgo:positions:IBKR_PED')
if pos:
    d = json.loads(pos.decode() if isinstance(pos, bytes) else pos)
    met = d.get('MET PRF', {})
    wfc = d.get('WFC PRY', {})
    axs = d.get('AXS PRE', {})
    print(f"\nIBKR_PED - MET PRF: qty={met.get('qty')}, befday={met.get('befday_qty')}")
    print(f"IBKR_PED - WFC PRY: qty={wfc.get('qty')}, befday={wfc.get('befday_qty')}")
    print(f"IBKR_PED - AXS PRE: qty={axs.get('qty')}, befday={axs.get('befday_qty')}")
