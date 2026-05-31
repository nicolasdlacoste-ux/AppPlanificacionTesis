import sys
import os
import json
import datetime
import time

# Añadir el path del proyecto
sys.path.append(os.path.abspath('.'))

from data_manager import DataManager
from poll_manager import PollingManager
from sync_manager import SyncWorker
from hydration_service import HydrationService, RealOtRepository
from poll_diagnostics import PollingDiagnosticReporter
import extractor

def run_test_4_local():
    print(f"\n=== SCENARIO: TEST 4 - LOCAL CHANGE ===")
    db = DataManager()
    
    # Factory para Google Service
    def _make_google_service():
        svc_cal, _ = extractor._safe_get_google_services()
        return svc_cal

    # 1. Modificar evento en SQLite
    # Usaremos el mismo Luis Rivera
    cal_id = "lrivera@akrimet.com"
    ev_id = "2cv57l81ofnvkcab88qufiirln"
    
    # Agregar vehículo
    ext = {"private": {"app_vehiculo": "TEST_VEHICLE_POL"}}
    db.actualizar_extended_props_incremental(ev_id, ext)
    print(f"Updated local event {ev_id} with vehicle metadata.")
    
    # 2. Encolar en sync_queue para que SyncWorker lo mande a Google
    import uuid
    queue_id = str(uuid.uuid4())
    with db._get_connection() as conn:
        conn.execute("""
            INSERT INTO sync_queue (queue_id, event_id, calendar_id, tecnico, operation, created_at, status) 
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
        """, (queue_id, ev_id, cal_id, "Luis Rivera", "UPDATE", datetime.datetime.now().isoformat()))
        conn.commit()
    
    # 3. Ejecutar SyncWorker (una pasada)
    print("Running SyncWorker...")
    worker = SyncWorker(db, extractor)
    # SyncWorker procesa la cola en un hilo, pero podemos llamar a su lógica directamente para el test
    worker.process_queue() 
    print("SyncWorker finished processing queue.")
    
    # 4. Ejecutar Polling
    ot_repo = RealOtRepository(db)
    hydrator = HydrationService(ot_repo)
    pm = PollingManager(db, google_service_factory=_make_google_service, hydration_service=hydrator)
    
    print("Running polling cycle...")
    pm._poll_all_calendars()
    
    # 5. Reporte
    reporter = PollingDiagnosticReporter(db, google_service_factory=_make_google_service)
    logs = db.get_poll_logs(limit=50)
    cycle_id = next((l["detail"].get("cycle_id") for l in logs if l["event_type"] == "POLLING:cycle_started"), None)
    
    if cycle_id:
        report = reporter.get_cycle_report(cycle_id)
        report_file = "scratch/report_test_4_local.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report saved to {report_file}")
    else:
        print("Cycle not found.")

if __name__ == "__main__":
    run_test_4_local()
