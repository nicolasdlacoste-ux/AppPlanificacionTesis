try:
    with open('data_manager.py', 'r', encoding='cp1252') as f:
        content = f.read()
    print("Read as cp1252 successfully.")
    
    # Encontrar el patron corrupto
    import re
    matches = re.findall(r'.{1}cnico', content)
    print(f"Found matches (cp1252): {[repr(m) for m in matches]}")
    
    # Reemplazar por Técnico normal
    new_content = re.sub(r'.{1}cnico', 'T\u00e9cnico', content)
    
    # Escribir SIEMPRE como UTF-8
    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Written as utf-8 successfully.")
except Exception as e:
    print(f"Error: {e}")
