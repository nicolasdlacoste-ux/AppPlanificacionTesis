import sqlite3
import os

db_path = "planificacion.db"
if not os.path.exists(db_path):
    print(f"Error: {db_path} no existe.")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM eventos")
    ev_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tecnicos")
    tec_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    
    print(f"Tablas: {', '.join(tables)}")
    print(f"Eventos: {ev_count}")
    print(f"Tecnicos: {tec_count}")
    
    if ev_count > 0:
        cursor.execute("SELECT id, summary, tecnico_nombre, inicio, fin FROM eventos LIMIT 5")
        print("\nEjemplos de eventos:")
        for row in cursor.fetchall():
            print(row)
            
    conn.close()
