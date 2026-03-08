
import os

log_file = 'app.log'
try:
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print("".join(lines[-50:]))
except Exception as e:
    print(f"Error reading log: {e}")
