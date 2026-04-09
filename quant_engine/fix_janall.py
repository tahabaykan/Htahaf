
import os

path = 'app/api/janall_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = 0
for i in range(len(lines)):
    if skip > 0:
        skip -= 1
        continue
    
    line = lines[i]
    
    # Fix get_orders (Line ~335)
    if "from app.api.trading_routes import get_positions_snapshot" in line:
        new_lines.append(line.replace("get_positions_snapshot", "get_positions"))
        continue
    if "pos_response = await get_positions_snapshot()" in line:
        new_lines.append(line.replace("get_positions_snapshot()", "get_positions()"))
        continue

    # Fix get_pending_orders (Line ~430) and get_filled_orders (Line ~493)
    if "from app.psfalgo.position_snapshot_api import get_position_snapshot_api" in line:
        # Check if next line is pos_api = ...
        if i + 1 < len(lines) and "pos_api = get_position_snapshot_api()" in lines[i+1]:
            # Replace the whole block until positions = ...
            new_lines.append(line.replace("from app.psfalgo.position_snapshot_api import get_position_snapshot_api", "from app.api.trading_routes import get_positions"))
            new_lines.append("        pos_response = await get_positions()\n")
            
            # Find where positions = ... starts and skip everything in between
            for j in range(i+2, len(lines)):
                if "positions = " in lines[j] and ".get('positions'" in lines[j]:
                    new_lines.append(lines[j].replace(".get('positions'", "pos_response.get('positions'"))
                    skip = j - i
                    break
            continue

    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Successfully patched app/api/janall_routes.py")
