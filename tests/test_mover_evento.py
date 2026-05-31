"""
Simula mover un evento a otro técnico para verificar que el UNIQUE constraint ya no falla.
"""
import sys; sys.path.insert(0, '.')
from data_manager import DataManager
import sqlite3, json

db = DataManager()

# Buscar dos técnicos distintos
conn = sqlite3.connect('planificacion.db')
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT tecnico_nombre, calendar_id FROM eventos WHERE tecnico_nombre IS NOT NULL LIMIT 5")
rows = cursor.fetchall()
conn.close()

if len(rows) < 2:
    print("SKIP: necesita al menos 2 técnicos distintos en la DB")
    exit()

# Buscar un evento del primer técnico
tec1_nombre, cal1 = rows[0]
tec2_nombre, cal2 = rows[1]

conn = sqlite3.connect('planificacion.db')
cursor = conn.cursor()
cursor.execute("SELECT id, tecnico_nombre, calendar_id, summary, version FROM eventos WHERE tecnico_nombre = ? LIMIT 1", (tec1_nombre,))
ev = cursor.fetchone()
conn.close()

if not ev:
    print(f"No hay eventos para {tec1_nombre}")
    exit()

ev_id, ev_tec, ev_cal, ev_summary, ev_version = ev
print(f"Evento: {ev_id[:20]}... tecnico={ev_tec}, cal={ev_cal}, version={ev_version}")
print(f"Moviendo a: {tec2_nombre} ({cal2})")

try:
    new_ver = db.actualizar_evento_individual(ev_id, ev_cal, {
        "tecnico":     tec2_nombre,
        "evento":      ev_summary,
        "inicio":      None,
        "fin":         None,
        "ubicacion":   "",
        "descripcion": "",
        "calendar_id": cal2,
        "extendedProperties": {}
    }, base_version=ev_version)
    print(f"OK — nueva version: {new_ver}")

    # Revertir al estado original para no dejar datos corruptos
    db.actualizar_evento_individual(ev_id, cal2, {
        "tecnico":     tec1_nombre,
        "evento":      ev_summary,
        "inicio":      None,
        "fin":         None,
        "ubicacion":   "",
        "descripcion": "",
        "calendar_id": ev_cal,
        "extendedProperties": {}
    })
    print(f"Revertido a {tec1_nombre} — test PASS")

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
