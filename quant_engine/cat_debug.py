
import sys

try:
    with open('debug_output_10.txt', 'r', encoding='utf-16-le') as f:
        print(f.read())
except Exception as e:
    print(f"Failed utf-16-le: {e}")
    try:
        with open('debug_output_10.txt', 'r', encoding='utf-8') as f:
            print(f.read())
    except Exception as e2:
        print(f"Failed utf-8: {e2}")
