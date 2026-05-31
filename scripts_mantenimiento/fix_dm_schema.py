import re

def fix_dm_schema():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Arreglar la locura de "ER TABLE te" -> "\u01f8" o similar
    # Parece que "ER TABLE te" fue reemplazado por "\u01f8" (Ǹ)
    
    # Intentar restaurar palabras clave de SQL
    content = content.replace('ALT\u01f8cnicos', 'ALTER TABLE tecnicos')
    content = content.replace('T\u01f8cnico_nombre', 'tecnico_nombre')
    content = content.replace('calendar_id tecnico_nombre TEXT', 'calendar_id TEXT, tecnico_nombre TEXT')
    content = content.replace('source tecnico_nombre)', 'source TEXT, tecnico_nombre TEXT')
    
    # También vi "TǸcnico" en los diccionarios.
    content = content.replace('T\u01f8cnico', 'T\u00e9cnico')

    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("data_manager.py schema and keys fixed.")

fix_dm_schema()
