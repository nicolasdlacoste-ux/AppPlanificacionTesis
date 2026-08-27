import os
import sys

sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from extractor import _safe_get_google_services

svc_cal, _ = _safe_get_google_services()

ev = svc_cal.events().get(calendarId='ndiaz@akrimet.com', eventId='5o4lvicj6ok6hvnejollrvuc9c').execute()
print("updated:", ev.get('updated'))
print("created:", ev.get('created'))
