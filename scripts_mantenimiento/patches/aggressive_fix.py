import re

def aggressive_fix():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazar CUALQUIER variante de T...cnico_nombre por tecnico_nombre
    content = re.sub(r'T[^c]*?cnico_nombre', 'tecnico_nombre', content)
    
    # Arreglar la declaraci\u00f3n de columnas
    # calendar_id tecnico_nombre TEXT -> calendar_id TEXT, tecnico_nombre TEXT
    content = content.replace('calendar_id tecnico_nombre TEXT', 'calendar_id TEXT, tecnico_nombre TEXT')
    
    # source tecnico_nombre), -> source TEXT, tecnico_nombre TEXT),
    content = content.replace('source tecnico_nombre),', 'source TEXT, tecnico_nombre TEXT),')
    
    # ALTER TABLE
    content = re.sub(r'ALT[^c]*?cnicos', 'ALTER TABLE tecnicos', content)
    
    # Keys en dicts
    content = re.sub(r'T[^c]*?cnico', 'T\u00e9cnico', content)

    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Aggressive fix completed.")

aggressive_fix()
