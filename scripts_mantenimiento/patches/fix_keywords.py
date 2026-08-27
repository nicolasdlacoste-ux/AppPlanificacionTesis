def fix_corrupted_keywords():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Arreglar palabras clave de SQL que fueron accidentalmente "estandarizadas" como Técnico
    content = content.replace('ALT\u00e9cnicos', 'ALTER TABLE tecnicos')
    content = content.replace('ALT\u00e9cnico', 'ALTER TABLE tecnico')
    
    # Asegurar que tecnico_nombre no est\u00e9 como T\u00e9cnico_nombre si no es intencional
    # (Aunque en el esquema ya lo puse como tecnico_nombre)
    
    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Corrupted SQL keywords fixed.")

fix_corrupted_keywords()
