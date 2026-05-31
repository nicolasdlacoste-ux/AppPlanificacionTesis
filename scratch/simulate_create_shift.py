import json
import sys
import datetime
import pytz

sys.path.append('.')
from utils import TimeNormalizationService
from sync_manager import map_evento_to_google

# 1. Simulate API Server input
fecha = "2026-05-15"
h_start = 10.0 # 10:00 AM
h_dur = 1.0

h_int = int(h_start)
m_int = int((h_start % 1) * 60)
h_fin_int = int(h_start + h_dur)
m_fin_int = int(((h_start + h_dur) % 1) * 60)

raw_local_time = f"{fecha}T{h_int:02d}:{m_int:02d}:00"
print(f"1. Frontend Input: {raw_local_time}")

# 2. API Server Normalization
inicio_str = TimeNormalizationService.normalize_to_utc_z(raw_local_time)
print(f"2. SQLite Persisted: {inicio_str}")

# 3. SyncWorker Mapping
event = {
    "id": "test_shift",
    "inicio": inicio_str,
    "fin": TimeNormalizationService.normalize_to_utc_z(f"{fecha}T{h_fin_int:02d}:{m_fin_int:02d}:00"),
    "tecnico_nombre": "Test",
    "summary": "Test Shift"
}

print("\n3. SyncWorker Mapping Logic:")
payload = map_evento_to_google(event)

google_start = payload["start"]["dateTime"]
print(f"4. Payload sent to Google: {google_start}")

# 5. Interpretation
print("\nInterpretation:")
if google_start.endswith("Z"):
    # Convert Z to Argentina to see what Google would show in Argentina
    utc_dt = datetime.datetime.fromisoformat(google_start.replace("Z", "+00:00"))
    arg_tz = pytz.timezone("America/Argentina/Buenos_Aires")
    local_dt = utc_dt.astimezone(arg_tz)
    print(f"   If Google shows this in ART (-03:00), it will be: {local_dt.strftime('%H:%M')}")
    if local_dt.hour == 10:
        print("   RESULT: CORRECT (10:00 AM)")
    else:
        print(f"   RESULT: INCORRECT (Shift of {local_dt.hour - 10} hours)")
