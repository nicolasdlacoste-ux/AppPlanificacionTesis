import os, re

text = open('api_server.py', encoding='utf-8').read()

old_str = '''            "sync_status": "PENDING",
            "pending_sync": 1
        }'''

new_str = '''            "sync_status": "PENDING",
            "pending_sync": 1,
            "version": 1
        }'''

if old_str in text:
    text = text.replace(old_str, new_str)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched version into event_obj!")
else:
    print("Could not find the block to replace!")
