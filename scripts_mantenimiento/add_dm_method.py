import json

def add_method_to_dm():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    insert_idx = -1
    for i, line in enumerate(lines):
        if 'def obtener_eventos_dict' in line:
            # Buscar el final de ese m\u00e9todo
            for j in range(i+1, len(lines)):
                if lines[j].startswith('    def ') or lines[j].startswith('    # '):
                    insert_idx = j
                    break
            break

    if insert_idx != -1:
        new_method = '''
    def obtener_eventos_por_fecha(self, fecha_str):
        """Retorna eventos que comienzan en una fecha espec\u00edfica (YYYY-MM-DD)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Buscamos eventos donde la fecha de Inicio empiece con la cadena dada
            cursor.execute("SELECT * FROM eventos WHERE Inicio LIKE ?", (f"{fecha_str}%",))
            rows = cursor.fetchall()
            eventos = []
            for r in rows:
                eventos.append({
                    "id": r[0],
                    "calendar_id": r[1],
                    "T\u00e9cnico": r[2],
                    "Evento": r[3],
                    "Inicio": r[4],
                    "Fin": r[5],
                    "Ubicaci\u00f3n": r[6],
                    "Descripci\u00f3n": r[7],
                    "extendedProperties": json.loads(r[8] or '{}'),
                    "version": r[9],
                    "sync_status": r[10],
                    "source": r[11]
                })
            return eventos
'''
        lines.insert(insert_idx, new_method)
        with open('data_manager.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("obtener_eventos_por_fecha added to data_manager.py")
    else:
        print("Could not find insertion point.")

add_method_to_dm()
