import sqlite3
import json
import os
import re

def cleanup_noise_events(db_path='planificacion.db'):
    if not os.path.exists(db_path):
        print(f"No se encontró la base de datos en {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Identificar eventos a borrar
    # Criterio: poll_source == 'google_poll' AND (Título en lista de ruido O Sin nro de OT)
    cursor.execute("SELECT id, summary, tecnico_nombre FROM eventos WHERE poll_source = 'google_poll'")
    rows = cursor.fetchall()

    noise_titles = ['Oficina', 'Campo', 'Home', 'Working Location', 'Fuera de la oficina', 'Tiempo de enfoque']
    to_delete = []

    print(f"Analizando {len(rows)} eventos provenientes de polling...")

    for eid, summary, tec in rows:
        is_noise = False
        
        # Caso A: Títulos de sistema conocidos
        if summary in noise_titles:
            is_noise = True
        
        # Caso B: No tiene número de OT (4 o más dígitos)
        elif not re.search(r'\d{4,}', summary):
            is_noise = True
        
        if is_noise:
            to_delete.append(eid)
            print(f"  [Marcado para borrar] {summary} ({tec}) - ID: {eid}")

    if not to_delete:
        print("No se encontraron eventos de ruido para eliminar.")
        conn.close()
        return

    print(f"\nProcediendo a eliminar {len(to_delete)} eventos...")

    # 2. Borrar de la tabla eventos
    cursor.executemany("DELETE FROM eventos WHERE id = ?", [(eid,) for eid in to_delete])
    
    # 3. Borrar de la cola de revisión (poll_review_queue)
    cursor.executemany("DELETE FROM poll_review_queue WHERE event_id = ?", [(eid,) for eid in to_delete])

    conn.commit()
    print("Limpieza completada exitosamente.")
    conn.close()

if __name__ == "__main__":
    cleanup_noise_events()
