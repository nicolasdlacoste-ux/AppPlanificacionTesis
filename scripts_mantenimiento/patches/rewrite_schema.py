def rewrite_schema():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    schema_block = '''
                cursor.execute(\'\'\'
                    CREATE TABLE eventos (
                        id TEXT,
                        calendar_id TEXT,
                        tecnico_nombre TEXT,
                        summary TEXT,
                        inicio TEXT,
                        fin TEXT,
                        ubicacion TEXT,
                        descripcion TEXT,
                        extended_props TEXT,
                        version INTEGER DEFAULT 1,
                        sync_status TEXT DEFAULT \'SYNCED\',
                        updated_at TEXT,
                        last_synced_at TEXT,
                        source TEXT,
                        PRIMARY KEY (id, tecnico_nombre),
                        FOREIGN KEY (tecnico_nombre) REFERENCES tecnicos (nombre)
                    )
                \'\'\')'''
    
    # Buscar el bloque CREATE TABLE eventos y reemplazarlo
    import re
    pattern = r"cursor\.execute\(\'\'\'\s+CREATE TABLE eventos \(.*?\)\s+\'\'\'\)"
    content = re.sub(pattern, schema_block, content, flags=re.DOTALL)
    
    # También arreglar el primer CREATE TABLE (el IF NOT EXISTS)
    pattern_if = r"cursor\.execute\(\'\'\'\s+CREATE TABLE IF NOT EXISTS eventos \(.*?\)\s+\'\'\'\)"
    content = re.sub(pattern_if, schema_block.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS'), content, flags=re.DOTALL)

    # Arreglar llaves de diccionarios
    content = re.sub(r'["\']T[^c]*?cnico["\']', '"T\u00e9cnico"', content)
    content = re.sub(r'["\']Ubicac[^n]*?n["\']', '"Ubicaci\u00f3n"', content)
    content = re.sub(r'["\']Descripc[^n]*?n["\']', '"Descripci\u00f3n"', content)

    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Schema rewritten successfully.")

rewrite_schema()
