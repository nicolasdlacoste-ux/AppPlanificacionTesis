import json
import sys
import sqlite3

sys.path.append('.')
from sync_manager import map_evento_to_google

def audit_event(event_id):
    conn = sqlite3.connect('planificacion.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos WHERE id=?", (event_id,))
    row = cursor.fetchone()
    if not row:
        print(f"Event {event_id} not found")
        return
    
    event = dict(row)
    print(f"\n--- AUDITING EVENT: {event_id} ---")
    payload = map_evento_to_google(event)
    print("\n--- END AUDIT ---")

if __name__ == "__main__":
    ids = ["local_481b9b25dc71", "local_08627153b333"]
    for eid in ids:
        audit_event(eid)
