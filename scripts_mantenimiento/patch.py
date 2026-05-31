import sys

def patch_file():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    old_dict = '''                    "Descripción": r[7],
                    "extendedProperties": json.loads(r[8]) if r[8] else {}
                })'''
    
    new_dict = '''                    "Descripción": r[7],
                    "extendedProperties": json.loads(r[8]) if r[8] else {},
                    "version": r[9] if len(r) > 9 else 1,
                    "sync_status": r[10] if len(r) > 10 else "SYNCED"
                })'''

    if old_dict in content:
        content = content.replace(old_dict, new_dict)
        with open('data_manager.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patch successful.")
    else:
        print("old_dict not found.")

patch_file()
