import os
import sys
import datetime

# Add current path
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from extractor import _safe_get_google_services

svc_cal, _ = _safe_get_google_services()

try:
    time_min = (datetime.datetime.utcnow() - datetime.timedelta(days=2)).isoformat() + "Z"
    events_result = svc_cal.events().list(calendarId='ndiaz@akrimet.com', timeMin=time_min, singleEvents=True, maxResults=50).execute()
    events = events_result.get('items', [])
    print("Found events via API:")
    for ev in events:
        if 'test' in ev.get('summary', '').lower() or 'Test' in ev.get('summary', ''):
            print(ev['summary'], ev['id'], ev.get('start'), ev.get('status'))
except Exception as e:
    print("Error:", str(e))
