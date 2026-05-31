import re

def final_final_fix(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazar CUALQUIER T...cnico por T\u00e9cnico
    content = re.sub(r'T[^c]{1,3}cnico', 'T\u00e9cnico', content)
    
    # Tambi\u00e9n Ubicaci\u00f3n y Descripci\u00f3n
    content = re.sub(r'Ubicaci[^n]{1,3}n', 'Ubicaci\u00f3n', content)
    content = re.sub(r'Descripci[^n]{1,3}n', 'Descripci\u00f3n', content)
    
    # Y t\u00e9cnico (min\u00fascula)
    content = re.sub(r't[^c]{1,3}cnico', 't\u00e9cnico', content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Final final fix for {filename} completed.")

final_final_fix('api_server.py')
final_final_fix('data_manager.py')
