import json

def add_vincular_method():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Buscar d\u00f3nde insertar (cerca de otros m\u00e9todos de eventos)
    insert_idx = -1
    for i, line in enumerate(lines):
        if 'def actualizar_titulo_evento' in line:
            # Buscar el final de ese m\u00e9todo
            for j in range(i+1, len(lines)):
                if lines[j].startswith('    def ') or lines[j].startswith('    # '):
                    insert_idx = j
                    break
            break

    if insert_idx != -1:
        new_method = '''
    def vincular_evento_a_grupo(self, event_id, grupo_id):
        """Actualiza las extendedProperties de un evento para incluir el grupo_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT extendedProperties FROM eventos WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            if row:
                props = json.loads(row[0] or '{}')
                if 'private' not in props: props['private'] = {}
                props['private']['grupo_id'] = grupo_id
                cursor.execute("UPDATE eventos SET extendedProperties = ? WHERE id = ?", (json.dumps(props), event_id))
                conn.commit()
'''
        lines.insert(insert_idx, new_method)
        with open('data_manager.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("vincular_evento_a_grupo added to data_manager.py")
    else:
        print("Could not find insertion point in data_manager.py")

add_vincular_method()
