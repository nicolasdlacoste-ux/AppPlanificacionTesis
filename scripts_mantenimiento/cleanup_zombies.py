import sqlite3

def cleanup_zombies():
    print("Iniciando limpieza de eventos 'zombies' y corrección de ownership...")
    
    conn = sqlite3.connect('planificacion.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Eliminar eventos estancados en "REVIEW_DELETE" si tienen un hermano activo
    cursor.execute("""
        SELECT id, google_event_id, calendar_id, tecnico_nombre 
        FROM eventos 
        WHERE sync_status != 'CANCELLED_IN_GOOGLE' 
          AND EXISTS (
              SELECT 1 FROM poll_review_queue 
              WHERE event_id = eventos.id 
                AND status = 'PENDING' 
                AND conflict_type = 'REMOTE_DELETE'
          )
    """)
    stuck_events = cursor.fetchall()
    
    deleted_count = 0
    for ev in stuck_events:
        # Verificar si hay hermanos activos
        cursor.execute("""
            SELECT id FROM eventos 
            WHERE google_event_id = ? 
              AND calendar_id != ? 
              AND sync_status != 'CANCELLED_IN_GOOGLE'
              AND id NOT IN (
                  SELECT event_id FROM poll_review_queue 
                  WHERE status = 'PENDING' AND conflict_type = 'REMOTE_DELETE'
              )
        """, (ev['google_event_id'], ev['calendar_id']))
        siblings = cursor.fetchall()
        
        if siblings:
            print(f"Borrando fantasma de {ev['tecnico_nombre']} ({ev['id']}) porque existe el hermano activo {siblings[0]['id']}")
            # Auto-aceptar la revisión
            cursor.execute("UPDATE poll_review_queue SET status = 'ACCEPTED' WHERE event_id = ? AND status = 'PENDING'", (ev['id'],))
            # Marcar el evento como CANCELLED_IN_GOOGLE
            cursor.execute("UPDATE eventos SET sync_status = 'CANCELLED_IN_GOOGLE' WHERE id = ?", (ev['id'],))
            deleted_count += 1

    # 2. Corregir Ownership Mismatches (Planner assigned to X, Calendar owner is Y)
    cursor.execute("""
        SELECT e.id, e.calendar_id, e.tecnico_nombre, t.nombre as verdadero_nombre
        FROM eventos e
        JOIN tecnicos t ON e.calendar_id = t.correo
        WHERE e.tecnico_nombre != t.nombre
    """)
    mismatches = cursor.fetchall()
    
    mismatch_count = 0
    for m in mismatches:
        print(f"Corrigiendo mismatch de ownership: {m['id']} estaba asignado a '{m['tecnico_nombre']}', se corrige a '{m['verdadero_nombre']}' (owner de {m['calendar_id']})")
        cursor.execute("UPDATE eventos SET tecnico_nombre = ? WHERE id = ?", (m['verdadero_nombre'], m['id']))
        mismatch_count += 1
        
    # 3. Eliminar eventos que tengan 'reassignment_in_progress' atascado
    
    conn.commit()
    conn.close()
    print(f"\nLimpieza completada:")
    print(f"- Eventos fantasmas eliminados por reasignación: {deleted_count}")
    print(f"- Mismatches de Ownership corregidos: {mismatch_count}")

if __name__ == '__main__':
    cleanup_zombies()
