import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_manager import DataManager
from sync_observatory import SyncObservatoryService

def test():
    db = DataManager("planificacion.db")
    obs = SyncObservatoryService(db)
    
    print("\n=== DASHBOARD SNAPSHOT ===")
    health = obs.get_dashboard_snapshot()
    print(json.dumps(health, indent=2))
    
    print("\n=== DRIFT REPORT ===")
    drift = obs.get_drift_report()
    print(json.dumps(drift, indent=2))
    
    print("\n=== RECONCILIATION LOGS (FIELD_OWNERSHIP) ===")
    logs = obs.get_reconciliation_decisions(limit=5)
    for l in logs:
        print(f"[{l['timestamp']}] {l['event_type']} - Event: {l['event_id']}")
        print(f"   Detail: {l['detail']}")

if __name__ == "__main__":
    test()
