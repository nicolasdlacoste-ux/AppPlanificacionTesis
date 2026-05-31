import re

def fix_api_keys():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Estandarizar llaves en api_server.py
    content = re.sub(r'["\']T[^c]*?cnico["\']', '"T\u00e9cnico"', content)
    content = re.sub(r'["\']Ubicac[^n]*?n["\']', '"Ubicaci\u00f3n"', content)
    content = re.sub(r'["\']Descripc[^n]*?n["\']', '"Descripci\u00f3n"', content)

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("api_server.py keys standardized.")

fix_api_keys()
