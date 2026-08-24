import sys

def patch_get_eventos():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = r'''                "extendedProperties": ev.get("extendedProperties", {}),
                "calendarId": ev.get("calendar_id", ""),
            })'''
    
    new_code = r'''                "extendedProperties": ev.get("extendedProperties", {}),
                "calendarId": ev.get("calendar_id", ""),
                "version": ev.get("version", 1),
                "sync_status": ev.get("sync_status", "SYNCED")
            })'''

    if old_code in content:
        content = content.replace(old_code, new_code)
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("get_eventos patched successfully.")
    else:
        print("Could not find get_eventos anchor in api_server.py")

patch_get_eventos()
