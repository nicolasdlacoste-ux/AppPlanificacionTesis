import re

def standardize_technician_key(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazar variantes de T\u00e9cnico (T\u01f8cnico, T\u00e9cnico, etc)
    # Buscamos T seguido de cualquier cosa que no sea c y luego cnico
    pattern = r'T[^c]*?cnico'
    
    # Queremos reemplazarlo por T\u00e9cnico (con acento normal)
    new_content = re.sub(pattern, "T\u00e9cnico", content)
    
    if content != new_content:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Standardized {filename}")
    else:
        print(f"No changes needed for {filename}")

standardize_technician_key('api_server.py')
standardize_technician_key('data_manager.py')
