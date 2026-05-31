import sys
import os
import time
import requests
import json
import datetime

# Añadir el path del proyecto para importar extractor
sys.path.append(os.path.abspath('.'))
import extractor

API_BASE = "http://localhost:8000/api"

def trigger_polling(dry_run=False):
    print(f"Triggering polling (dry_run={dry_run})...")
    resp = requests.post(f"{API_BASE}/poll/trigger?dry_run={str(dry_run).lower()}")
    return resp.json()

def get_latest_report():
    print("Fetching latest report...")
    resp = requests.get(f"{API_BASE}/poll/report/latest")
    return resp.json()

def test_1_safe_change(service, calendar_id, event_id):
    print("\n--- TEST 1: SAFE change (description) ---")
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    original_desc = event.get('description', '')
    new_desc = f"{original_desc}\n[TEST_SAFE_CHANGE] {datetime.datetime.now().isoformat()}"
    event['description'] = new_desc
    service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    print(f"Updated description in Google for {event_id}")
    
    time.sleep(2) # Esperar propagación Google
    trigger_polling()
    time.sleep(5) # Esperar procesamiento polling
    
    report = get_latest_report()
    # Guardar resultado
    with open('scratch/test_1_result.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Test 1 completed. Report saved.")

def test_2_critical_change(service, calendar_id, event_id):
    print("\n--- TEST 2: CRITICAL change (summary) ---")
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    original_summary = event.get('summary', '')
    new_summary = f"[MODIFIED] {original_summary}"
    event['summary'] = new_summary
    service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    print(f"Updated summary in Google for {event_id}")
    
    time.sleep(2)
    trigger_polling()
    time.sleep(5)
    
    report = get_latest_report()
    with open('scratch/test_2_result.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Test 2 completed. Report saved.")

def test_3_delete(service, calendar_id, event_id):
    print("\n--- TEST 3: DELETE in Google ---")
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    print(f"Deleted event in Google: {event_id}")
    
    time.sleep(2)
    trigger_polling()
    time.sleep(5)
    
    report = get_latest_report()
    with open('scratch/test_3_result.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Test 3 completed. Report saved.")

def test_5_new_event(service, calendar_id):
    print("\n--- TEST 5: NEW event in Google ---")
    new_event = {
        'summary': '8511 (AYUDIN) - TEST NUEVO',
        'start': {'dateTime': '2026-05-15T09:00:00-03:00', 'timeZone': 'America/Argentina/Buenos_Aires'},
        'end': {'dateTime': '2026-05-15T12:00:00-03:00', 'timeZone': 'America/Argentina/Buenos_Aires'},
    }
    created = service.events().insert(calendarId=calendar_id, body=new_event).execute()
    print(f"Created new event in Google: {created['id']}")
    
    time.sleep(2)
    trigger_polling()
    time.sleep(5)
    
    report = get_latest_report()
    with open('scratch/test_5_result.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Test 5 completed. Report saved.")

if __name__ == "__main__":
    # Usar el primer evento de list_events.py
    # ID: 2cv57l81ofnvkcab88qufiirln | CAL: lrivera@akrimet.com
    cal_id = "lrivera@akrimet.com"
    ev_id = "2cv57l81ofnvkcab88qufiirln"
    ev_id_2 = "2fsllrnh7ep0l8uhcle8kjmd8s"
    ev_id_3 = "7t8fpgsfhh6vaesdfvrfba3hcl"
    
    svc_cal, _ = extractor._safe_get_google_services()
    
    try:
        test_1_safe_change(svc_cal, cal_id, ev_id)
        test_2_critical_change(svc_cal, cal_id, ev_id_2)
        test_3_delete(svc_cal, cal_id, ev_id_3)
        test_5_new_event(svc_cal, cal_id)
    except Exception as e:
        print(f"Error during tests: {e}")
        import traceback
        traceback.print_exc()
