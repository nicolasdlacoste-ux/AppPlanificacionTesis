import requests
import json

def audit_api():
    try:
        # Assuming the server is running on localhost:8000
        # If not, I'll just simulate the call again with more detail
        print("--- API AUDIT (Simulated) ---")
        import sys
        import os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from data_manager import DataManager
        from utils import EventAdapter
        
        db = DataManager("planificacion.db")
        eventos_raw = db.obtener_eventos_dict()
        canon_events = [EventAdapter.sqlite_to_canonical(ev) for ev in eventos_raw]
        
        print(f"Total events in response: {len(canon_events)}")
        if len(canon_events) > 0:
            ev = canon_events[0]
            print(f"First event keys: {list(ev.keys())}")
            print(f"First event data sample:")
            print(f"  id: {ev.get('id')}")
            print(f"  summary: {ev.get('summary')}")
            print(f"  inicio (new name?): {ev.get('inicio')}")
            print(f"  start (old name?): {ev.get('start')}")
            
    except Exception as e:
        print(f"API Audit failed: {e}")

if __name__ == "__main__":
    audit_api()
