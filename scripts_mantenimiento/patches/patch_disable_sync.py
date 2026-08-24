import sys
import re

def disable_syncworker():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Buscar y comentar el start()
    pattern = r"(sync_worker\.start\(\))"
    replacement = r"# \1"
    
    if "sync_worker.start()" in content and "# sync_worker.start()" not in content:
        content, count = re.subn(pattern, replacement, content)
        if count > 0:
            with open('api_server.py', 'w', encoding='utf-8') as f:
                f.write(content)
            print("SyncWorker disabled.")
        else:
            print("Could not disable SyncWorker.")
    else:
        print("SyncWorker already disabled or not found.")

disable_syncworker()
