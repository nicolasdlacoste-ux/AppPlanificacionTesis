import re

def standardize_other_keys(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'Ubicac[^n]*?n', "Ubicaci\u00f3n", content)
    content = re.sub(r'Descripc[^n]*?n', "Descripci\u00f3n", content)
    content = re.sub(r'T[^c]*?cnico', "T\u00e9cnico", content)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Standardized other keys in {filename}")

standardize_other_keys('api_server.py')
standardize_other_keys('data_manager.py')
