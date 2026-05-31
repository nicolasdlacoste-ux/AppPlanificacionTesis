import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_manager import DataManager
from utils import EventAdapter

def audit_backend():
    db = DataManager("planificacion.db")
    
    # 1. Capa DataManager
    eventos_raw = db.obtener_eventos_dict()
    print(f"--- BACKEND AUDIT ---")
    print(f"DataManager RAW count: {len(eventos_raw)}")
    
    # 2. Capa EventAdapter
    try:
        canon_events = [EventAdapter.sqlite_to_canonical(ev) for ev in eventos_raw]
        print(f"EventAdapter CANONICAL count: {len(canon_events)}")
        
        if len(canon_events) > 0:
            first = canon_events[0]
            print("\nSAMPLE CANONICAL EVENT:")
            # Print keys to see if there's any "extra" metadata from observatory
            print(f"Keys: {list(first.keys())}")
            
            # Check for non-serializable fields
            try:
                json.dumps(first)
                print("JSON Serialization: OK")
            except Exception as je:
                print(f"JSON Serialization: FAILED - {je}")
                
            # Check timestamps
            print(f"Start: {first.get('start')}")
            print(f"End: {first.get('end')}")
            
            # Check app_ots
            print(f"OTs: {first.get('app_ots')}")
            
    except Exception as e:
        import traceback
        print(f"EventAdapter FAILED: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    audit_backend()
