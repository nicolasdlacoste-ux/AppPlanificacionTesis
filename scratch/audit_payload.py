import json
import sys
import datetime

# Mock _now_iso if not importable
def _now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

# Import from sync_manager
sys.path.append('.')
from sync_manager import map_evento_to_google

# Mock event that would come from api_server.py / Planner
# Scenario: A new event created in the Planner
mock_event = {
    "id": "local_1234567890",
    "summary": "Auditoría Servicio Técnico",
    "inicio": "2026-05-15T10:00:00", # Example start
    "fin": "2026-05-15T12:00:00",    # Example end
    "tecnico_nombre": "Técnico de Prueba",
    "calendar_id": "tecnico@ejemplo.com",
    "extended_props": json.dumps({
        "private": {
            "app_ots": json.dumps(["OT-123"]),
            "app_patrones": json.dumps(["Patrón-A"]),
            "app_vehiculo": "Camioneta 1"
        }
    }),
    "version": 1,
    "sync_status": "PENDING"
}

print("--- REPRODUCTION START ---")
try:
    payload = map_evento_to_google(mock_event)
    print("\n--- RESULTING PAYLOAD ---")
    print(json.dumps(payload, indent=2))
except Exception as e:
    print(f"\n!!! MAPPING FAILED: {e}")
    traceback.print_exc()

# Scenario: Event with missing 'inicio' or 'fin'
mock_event_broken = mock_event.copy()
mock_event_broken["inicio"] = ""
print("\n--- BROKEN SCENARIO (missing inicio) ---")
try:
    payload = map_evento_to_google(mock_event_broken)
except Exception as e:
    print(f"!!! Expected Error caught: {e}")

# Scenario: Event with different key for start/end
mock_event_legacy = {
    "id": "legacy_999",
    "Evento": "Servicio Legacy",
    "Inicio": "2026-05-16T09:00:00",
    "Fin": "2026-05-16T10:00:00",
    "sync_status": "PENDING"
}
print("\n--- LEGACY SCENARIO ---")
try:
    payload = map_evento_to_google(mock_event_legacy)
    print(json.dumps(payload, indent=2))
except Exception as e:
    print(f"!!! Mapping failed: {e}")
