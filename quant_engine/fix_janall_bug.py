
import os

path = 'app/api/janall_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the bug I introduced
content = content.replace("snapshotpos_response.get('positions', [])", "pos_response.get('positions', [])")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed the typo in app/api/janall_routes.py")
