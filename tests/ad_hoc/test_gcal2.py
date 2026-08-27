import os
import sys

# Add current path
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from extractor import _safe_get_google_services

svc_cal, _ = _safe_get_google_services()

try:
    events_result = svc_cal.events().list(calendarId='ndiaz@akrimet.com', q='test', singleEvents=True, maxResults=10).execute()
    events = events_result.get('items', [])
    print("Found events via API:")
    for ev in events:
        print(ev['summary'], ev['id'], ev.get('start'), ev.get('status'))
except Exception as e:
    print("Error:", str(e))
