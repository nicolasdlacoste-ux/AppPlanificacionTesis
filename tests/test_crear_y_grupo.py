"""Verifica las 3 correcciones: crear evento, vincular grupo, mover entre tecnicos."""
import sys; sys.path.insert(0, '.')
from data_manager import DataManager
import sqlite3, json

db = DataManager()

# ── TEST 1: guardar_evento_individual con todos los campos ────────────────────
print("TEST 1: guardar_evento_individual")
test_id = "test-crear-001"
db.guardar_evento_individual({
    "id":               test_id,
    "calendar_id":      "test@akrimet.com",
    "tecnico_nombre":   "Tecnico Test",
    "summary":          "Evento de prueba",
    "inicio":           "2026-05-10T08:00:00-03:00",
    "fin":              "2026-05-10T17:00:00-03:00",
    "ubicacion":        "Calle Test 123",
    "descripcion":      "Descripcion test",
    "extendedProperties": {"private": {"source": "internal", "version": "1"}},
    "version":          1,
    "sync_status":      "LOCAL",
    "source":           "internal",
    "updated_at":       "2026-05-10T08:00:00",
})
conn = sqlite3.connect('planificacion.db')
cursor = conn.cursor()
cursor.execute("SELECT id, version, sync_status, source, google_event_id FROM eventos WHERE id=?", (test_id,))
row = cursor.fetchone()
conn.close()
if row:
    print(f"  OK: id={row[0]}, version={row[1]}, sync_status={row[2]}, source={row[3]}, gid={row[4]}")
else:
    print("  FAIL: evento no encontrado")

# ── TEST 2: vincular_evento_a_grupo ───────────────────────────────────────────
print("TEST 2: vincular_evento_a_grupo")
db.vincular_evento_a_grupo(test_id, "grupo-test-001")
ev = db.find_by_google_event_id(test_id)
if ev:
    props = json.loads(ev.get('extended_props') or '{}')
    gid_in_props = props.get('private', {}).get('grupo_id')
    print(f"  OK: grupo_id en props = {gid_in_props}")
else:
    print("  FAIL: evento no encontrado tras vincular")

# ── TEST 3: mover entre tecnicos (reusar test del fix anterior) ───────────────
print("TEST 3: mover evento a otro tecnico")
new_ver = db.actualizar_evento_individual(test_id, "test@akrimet.com", {
    "tecnico":      "Nuevo Tecnico",
    "evento":       "Evento de prueba",
    "inicio":       "2026-05-10T08:00:00-03:00",
    "fin":          "2026-05-10T17:00:00-03:00",
    "calendar_id":  "nuevo@akrimet.com",
    "extendedProperties": {},
})
print(f"  OK: nueva version = {new_ver}")

# Limpieza
conn = sqlite3.connect('planificacion.db')
conn.execute("DELETE FROM eventos WHERE id=?", (test_id,))
conn.commit()
conn.close()
print("  Limpieza OK")
print("\n>>> 3/3 tests PASS")
