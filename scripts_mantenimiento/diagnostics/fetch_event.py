import os
import sys
sys.path.append(os.getcwd())
import extractor

svc_cal, _ = extractor._safe_get_google_services()
try:
    ev = svc_cal.events().get(calendarId='lrivera@akrimet.com', eventId='56f2qi1sch8l852noe22tcj4pe').execute()
    print("ATTENDEES:", ev.get('attendees'))
    print("STATUS:", ev.get('status'))
except Exception as e:
    print(e)
