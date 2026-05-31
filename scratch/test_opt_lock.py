import sys
import sqlite3
import json

sys.path.append('.')
from data_manager import DataManager, VersionConflictError

db = DataManager('planificacion.db')

# Setup test event
event_id = "test_opt_lock"
tec = "Test Tech"
cal = "test@example.com"

# Clean up
with db._get_connection() as conn:
    conn.execute("DELETE FROM eventos WHERE id=?", (event_id,))
    conn.commit()

# 1. First save
print("--- TEST 1: Initial Save ---")
db.guardar_evento_individual({
    "id": event_id,
    "tecnico_nombre": tec,
    "calendar_id": cal,
    "summary": "Original",
    "inicio": "2026-05-11T10:00:00Z",
    "fin": "2026-05-11T11:00:00Z"
})

ev = db.get_evento_dict(event_id, tec)
v1 = ev.get('version')
print(f"Version after first save: {v1}")

# 2. Correct update
print("\n--- TEST 2: Correct Update (v1 -> v2) ---")
v2 = db.actualizar_evento_individual(event_id, cal, {"tecnico": tec, "evento": "Updated"}, base_version=v1)
print(f"Version after update: {v2}")

# 3. Conflict update (trying to update with v1 again)
print("\n--- TEST 3: Conflict Update (trying v1 again) ---")
try:
    db.actualizar_evento_individual(event_id, cal, {"tecnico": tec, "evento": "Conflict"}, base_version=v1)
    print("!!! ERROR: Should have raised VersionConflictError")
except VersionConflictError as e:
    print(f"PASS: Caught expected conflict: {e}")

# 4. Legacy update (no base_version)
print("\n--- TEST 4: Legacy Update (no base_version) ---")
v3 = db.actualizar_evento_individual(event_id, cal, {"tecnico": tec, "evento": "Legacy"})
print(f"Version after legacy update: {v3} (Success)")

# Final check
final_ev = db.get_evento_dict(event_id, tec)
print(f"\nFinal Event State: {json.dumps(final_ev, indent=2)}")
