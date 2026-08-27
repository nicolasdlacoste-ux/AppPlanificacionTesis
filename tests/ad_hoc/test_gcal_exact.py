import os
import sys

sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from extractor import _safe_get_google_services

svc_cal, _ = _safe_get_google_services()

try:
    ev = svc_cal.events().get(calendarId='ndiaz@akrimet.com', eventId='5o4lvicj6ok6hvnejollrvuc9c').execute()
    print("Found exact event in ndiaz calendar:")
    print(ev['summary'], ev['id'], ev.get('start'), ev.get('status'))
except Exception as e:
    print("Error:", str(e))
