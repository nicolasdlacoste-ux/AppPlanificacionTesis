import sqlite3
import os

print("Limpiando la base de datos...")
conn = sqlite3.connect('planificacion.db')
cursor = conn.cursor()

cursor.execute("DELETE FROM eventos")
cursor.execute("DELETE FROM poll_review_queue")
cursor.execute("DELETE FROM poll_calendar_state")
conn.commit()

print("Ejecutando force_sync.py...")
import force_sync
force_sync.run_sync()

print("Aceptando todos los reviews creados...")
from data_manager import DataManager
db = DataManager()
db._db_path = 'planificacion.db' # asegurarnos de que usa la misma

conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT review_id FROM poll_review_queue WHERE status = 'PENDING'").fetchall()

print(f"Aceptando {len(rows)} reviews...")
success = 0
for r in rows:
    try:
        db.accept_review(r['review_id'])
        success += 1
    except Exception as e:
        print(f"Error con review {r['review_id']}: {e}")

print(f"Aceptados {success}/{len(rows)} reviews.")
