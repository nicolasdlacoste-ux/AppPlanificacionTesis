import sqlite3
import json

def list_events():
    conn = sqlite3.connect('planificacion.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, google_event_id, calendar_id, tecnico_nombre, summary FROM eventos WHERE google_event_id IS NOT NULL LIMIT 5")
    rows = cursor.fetchall()
    for r in rows:
        print(f"ID: {r[0]} | GID: {r[1]} | CAL: {r[2]} | TEC: {r[3]} | SUM: {r[4]}")
    conn.close()

if __name__ == "__main__":
    list_events()
