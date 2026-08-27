def rewrite_method():
    with open('data_manager.py', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if 'def obtener_eventos_dict(self):' in line:
            start_idx = i
        if start_idx != -1 and i > start_idx and 'return eventos' in line:
            end_idx = i + 1
            break

    if start_idx != -1 and end_idx != -1:
        new_method = '''    def obtener_eventos_dict(self):
        """Retorna los eventos en el formato original de la app (lista de dicts)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eventos")
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
                    "extendedProperties": json.loads(r[8]) if r[8] else {},
                    "version": r[9] if len(r) > 9 else 1,
                    "sync_status": r[10] if len(r) > 10 else "SYNCED"
                })
            return eventos
'''
        lines = lines[:start_idx] + [new_method] + lines[end_idx:]
        with open('data_manager.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("Method rewritten successfully.")

rewrite_method()
