import sys
import os
import json
import datetime
import time

# Añadir el path del proyecto
sys.path.append(os.path.abspath('.'))

from data_manager import DataManager
from poll_manager import PollingManager
from hydration_service import HydrationService, RealOtRepository
from poll_diagnostics import PollingDiagnosticReporter
import extractor

def run_test_scenario(scenario_name, action_fn):
    print(f"\n=== SCENARIO: {scenario_name} ===")
    db = DataManager()
    
    # Factory para Google Service
    def _make_google_service():
        svc_cal, _ = extractor._safe_get_google_services()
        return svc_cal

    ot_repo = RealOtRepository(db)
    hydrator = HydrationService(ot_repo)
    
    pm = PollingManager(
        db=db,
        google_service_factory=_make_google_service,
        hydration_service=hydrator
    )
    
    reporter = PollingDiagnosticReporter(db, google_service_factory=_make_google_service)
    
    # 1. Ejecutar acción en Google (o Local)
    svc = _make_google_service()
    target_id = action_fn(svc)
    
    # 2. Ejecutar Polling
    print("Running polling cycle...")
    pm._poll_all_calendars()
    
    # 3. Obtener el último ciclo de los logs
    logs = db.get_poll_logs(limit=100)
    cycle_id = None
    for l in logs:
        if l["event_type"] == "POLLING:cycle_started":
            cycle_id = l["detail"].get("cycle_id")
            break
    
    if not cycle_id:
        print("Error: Could not find cycle_id in logs.")
        return
    
    print(f"Cycle ID: {cycle_id}")
    report = reporter.get_cycle_report(cycle_id)
    
    # Guardar reporte
    report_file = f"scratch/report_{scenario_name.lower().replace(' ', '_')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"Report saved to {report_file}")
    return report

# --- Acciones para los tests ---

def action_test_1(svc):
    # SAFE change (description)
    cal_id = "lrivera@akrimet.com"
    ev_id = "2cv57l81ofnvkcab88qufiirln"
    event = svc.events().get(calendarId=cal_id, eventId=ev_id).execute()
    event['description'] = (event.get('description', '') + f"\n[TEST_SAFE] {datetime.datetime.now()}").strip()
    svc.events().update(calendarId=cal_id, eventId=ev_id, body=event).execute()
    print(f"Updated description for {ev_id}")
    return ev_id

def action_test_2(svc):
    # CRITICAL change (summary)
    cal_id = "lrivera@akrimet.com"
    ev_id = "2fsllrnh7ep0l8uhcle8kjmd8s"
    event = svc.events().get(calendarId=cal_id, eventId=ev_id).execute()
    event['summary'] = f"[MODIFIED] {event.get('summary', 'Sin titulo')}"
    svc.events().update(calendarId=cal_id, eventId=ev_id, body=event).execute()
    print(f"Updated summary for {ev_id}")
    return ev_id

def action_test_3(svc):
    # DELETE
    cal_id = "lrivera@akrimet.com"
    ev_id = "7t8fpgsfhh6vaesdfvrfba3hcl"
    svc.events().delete(calendarId=cal_id, eventId=ev_id).execute()
    print(f"Deleted event {ev_id}")
    return ev_id

def action_test_5(svc):
    # NEW event
    cal_id = "lrivera@akrimet.com"
    new_event = {
        'summary': '8131 (VALVULAS) - TEST NUEVO POLLING',
        'start': {'dateTime': '2026-05-20T10:00:00-03:00', 'timeZone': 'America/Argentina/Buenos_Aires'},
        'end': {'dateTime': '2026-05-20T14:00:00-03:00', 'timeZone': 'America/Argentina/Buenos_Aires'},
    }
    created = svc.events().insert(calendarId=cal_id, body=new_event).execute()
    print(f"Created event {created['id']}")
    return created['id']

if __name__ == "__main__":
    try:
        run_test_scenario("TEST_1_SAFE", action_test_1)
        time.sleep(2)
        run_test_scenario("TEST_2_CRITICAL", action_test_2)
        time.sleep(2)
        run_test_scenario("TEST_3_DELETE", action_test_3)
        time.sleep(2)
        run_test_scenario("TEST_5_NEW", action_test_5)
    except Exception as e:
        import traceback
        traceback.print_exc()
