import json
import sys
import datetime

sys.path.append('.')
from sync_manager import map_evento_to_google

# Exact data for local_40372b81fd64
event_403 = {
    "id": "local_40372b81fd64",
    "calendar_id": "ndiaz@akrimet.com",
    "tecnico_nombre": "Nicolás Díaz",
    "summary": "8775 (DROGUERIA VORS)",
    "inicio": "2026-05-05T07:00:00-03:00",
    "fin": "2026-05-05T16:00:00-03:00",
    "ubicacion": "Quintana 4680, CABA, Buenos Aires  Argentina",
    "descripcion": "",
    "extended_props": "{\"private\": {\"app_ots\": \"[\\\"8775\\\"]\", \"app_patrones\": \"[]\", \"source\": \"internal\", \"version\": \"1\"}}",
    "sync_status": "FAILED"
}

print("--- AUDIT FOR local_40372b81fd64 ---")
try:
    payload = map_evento_to_google(event_403)
    print("\n--- FINAL PAYLOAD ---")
    print(json.dumps(payload, indent=2))
except Exception as e:
    print(f"\n!!! MAPPING FAILED: {e}")

# Exact data for local_d682aab8b6a1
event_d68 = {
    "id": "local_d682aab8b6a1",
    "calendar_id": "nmedina@akrimet.com",
    "tecnico_nombre": "Norberto Medina",
    "summary": "8867 (MABXIENCE SAU)",
    "inicio": "2026-05-05T07:00:00-03:00",
    "fin": "2026-05-05T16:00:00-03:00",
    "ubicacion": "Carlos Villate 5148, Munro, Buenos Aires 1605 Argentina",
    "descripcion": "",
    "extended_props": "{\"private\": {\"app_ots\": \"[\\\"8867\\\"]\", \"app_patrones\": \"[]\", \"source\": \"internal\", \"version\": \"1\"}}",
    "sync_status": "FAILED"
}

print("\n--- AUDIT FOR local_d682aab8b6a1 ---")
try:
    payload = map_evento_to_google(event_d68)
    print("\n--- FINAL PAYLOAD ---")
    print(json.dumps(payload, indent=2))
except Exception as e:
    print(f"\n!!! MAPPING FAILED: {e}")
