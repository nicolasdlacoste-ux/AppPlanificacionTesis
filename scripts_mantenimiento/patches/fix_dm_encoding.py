def fix_dm_encoding():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Corregir las claves en el m\u00e9todo que agregu\u00e9
    old_block = '''                    "T\u00e9cnico": r[2],
                    "Evento": r[3],
                    "Inicio": r[4],
                    "Fin": r[5],
                    "Ubicaci\u00f3n": r[6],
                    "Descripci\u00f3n": r[7],'''
    
    # Usar los caracteres exactos que usa el resto del archivo
    new_block = '''                    "TǸcnico": r[2],
                    "Evento": r[3],
                    "Inicio": r[4],
                    "Fin": r[5],
                    "Ubicacin": r[6],
                    "Descripcin": r[7],'''
    
    content = content.replace(old_block, new_block)
    
    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("data_manager.py keys corrected to match existing encoding.")

fix_dm_encoding()
