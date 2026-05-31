import json
import datetime
from data_manager import DataManager
from sync_observatory import SyncObservatoryService

def generate_report():
    print("Iniciando Validación de Drift (FASE 2)...")
    db = DataManager("planificacion.db")
    obs = SyncObservatoryService(db)
    
    # 1. Snapshot del Dashboard
    snapshot = obs.get_dashboard_snapshot()
    print(f"\n[DASHBOARD_SNAPSHOT]")
    print(json.dumps(snapshot, indent=2))
    
    # 2. Reporte de Drift
    drift = obs.get_drift_report()
    print(f"\n[DRIFT_REPORT] Found {drift['drift_count']} issues")
    for item in drift["items"]:
        print(f"  - {item['summary']} ({item['tecnico']}): {item['issue']} | State: {item['sync_state']}")
    
    # 3. Decisiones de Reconciliación Recientes
    decisions = obs.get_reconciliation_decisions(limit=10)
    print(f"\n[RECENT_DECISIONS]")
    for d in decisions:
        detail_str = json.dumps(d['detail'], ensure_ascii=False) if isinstance(d['detail'], dict) else str(d['detail'])
        print(f"  - {d['timestamp']} | {d['event_type']} | {detail_str[:100]}...")

    # 4. Análisis de Timestamps Stale
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, summary, updated_at, last_synced_at FROM eventos WHERE updated_at < datetime('now', '-7 days')")
        stale = cursor.fetchall()
        print(f"\n[STALE_EVENTS] Found {len(stale)} events older than 7 days")
        for s in stale[:10]:
            print(f"  - {s[1]}: Last Update={s[2]}, Last Sync={s[3]}")

    print("\nValidación finalizada.")

if __name__ == "__main__":
    generate_report()
