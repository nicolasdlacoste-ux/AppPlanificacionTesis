import json
import sys
import datetime

sys.path.append('.')
from sync_manager import map_evento_to_google
from utils import TimeNormalizationService

# Scenario: New event with local time string (naive)
raw_event = {
    "id": "local_test_norm",
    "summary": "Prueba Normalización",
    "inicio": "2026-05-20T14:00:00", # Naive
    "fin": "2026-05-20T16:00:00",    # Naive
    "sync_status": "PENDING"
}

print("--- AUDIT START: TimeNormalizationService ---")
norm_inicio = TimeNormalizationService.normalize_to_utc_z(raw_event["inicio"])
norm_fin    = TimeNormalizationService.normalize_to_utc_z(raw_event["fin"])
print(f"Original Inicio: {raw_event['inicio']} -> Normalized: {norm_inicio}")
print(f"Original Fin:    {raw_event['fin']} -> Normalized: {norm_fin}")

print("\n--- GOOGLE PAYLOAD AUDIT ---")
payload = map_evento_to_google(raw_event)
print(json.dumps(payload, indent=2))

# Verify 'timeZone' is absent
start_obj = payload.get("start", {})
if "timeZone" in start_obj:
    print("!!! WARNING: 'timeZone' still present in payload")
else:
    print("PASS: 'timeZone' successfully removed from payload")

if start_obj.get("dateTime", "").endswith("Z"):
    print("PASS: 'dateTime' correctly suffixed with 'Z'")
else:
    print("!!! FAILURE: 'dateTime' missing 'Z' suffix")
