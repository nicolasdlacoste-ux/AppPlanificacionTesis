import json
import datetime
from data_manager import DataManager
from sync_observatory import SyncObservatoryService

def generate_final_report():
    print(">>> GENERANDO REPORTE FINAL DE OPERACIN - FASE 2")
    db = DataManager("planificacion.db")
    obs = SyncObservatoryService(db)
    
    # 1. Heartbeat check
    hb = obs.get_last_heartbeat()
    print(f"\n[POLLING_HEARTBEAT] Status: {'ALIVE' if hb else 'MISSING'}")
    if hb:
        print(f"  Cycle ID: {hb['detail'].get('cycle_id')}")
        print(f"  Last Run: {hb['timestamp']}")
        print(f"  Duration: {hb['detail'].get('duration_ms')}ms")
        print(f"  Metrics: {json.dumps(hb['detail'].get('metrics'), indent=2)}")
    
    # 2. Checklist Verification
    logs = db.get_poll_logs(limit=20, event_type="POLL_STARTUP")
    if logs:
        startup = logs[0]
        print(f"\n[POLL_STARTUP] Last Startup Checklist:")
        checklist = startup["detail"].get("checklist", {})
        for check, res in checklist.items():
            print(f"  - {check:25s}: {res}")
    
    # 3. Anti-Loop Effectiveness
    al_logs = db.get_poll_logs(limit=10, event_type="POLL_INBOUND_TRACE")
    anti_loops = [l for l in al_logs if l["detail"].get("decision") == "ANTI_LOOP_SKIP"]
    print(f"\n[ANTI_LOOP] Skips detected: {len(anti_loops)} (in last 10 traces)")
    
    # 4. Reconciliation Behavior
    rec_logs = obs.get_recent_inbound_traces(limit=20)
    print(f"\n[RECONCILIATION] Recent decisions:")
    for r in rec_logs:
        det = r["detail"]
        print(f"  - {r['timestamp']} | {det.get('google_event_id')[:10]}... | {det.get('decision')} | {det.get('persistence')}")

    # 5. Drift Report
    drift = obs.get_drift_report()
    print(f"\n[DRIFT] Found {drift['drift_count']} orphan or failed events.")
    
    # 6. Lag Report
    lag = obs.get_sync_lag()
    print(f"\n[SYNC_LAG] Found {len(lag)} pending syncs.")
    for l in lag[:5]:
        print(f"  - {l['summary']} | Local: {l['last_local_update']}")

    print("\n>>> FIN DEL REPORTE")

if __name__ == "__main__":
    generate_final_report()
