import sqlite3
import json

c = sqlite3.connect('planificacion.db')
c.row_factory = sqlite3.Row

def query(sql):
    res = c.execute(sql).fetchall()
    for r in res:
        print(dict(r))

print("--- Recent events with Testt ---")
query("SELECT id, summary, sync_state, sync_status, google_event_id, pending_sync FROM eventos WHERE summary LIKE '%Testt%' LIMIT 5")

print("\n--- Recent reviews ---")
query("SELECT review_id, event_id, conflict_type, status, detected_at FROM poll_review_queue ORDER BY detected_at DESC LIMIT 5")

print("\n--- Any cancelled events ---")
query("SELECT id, summary, sync_state, sync_status, google_event_id FROM eventos WHERE sync_state = 'CANCELLED_IN_GOOGLE' LIMIT 5")
