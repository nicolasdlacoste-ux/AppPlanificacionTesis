import sqlite3
c = sqlite3.connect('planificacion.db')

print("\n--- EVENTS ERROR ---")
for row in c.execute("SELECT id, summary, sync_error FROM eventos WHERE sync_status='ERROR' ORDER BY updated_at DESC LIMIT 5"):
    print(row)

print("\n--- LAST SYNC LOGS ---")
for row in c.execute("SELECT event_id, target, operation, status, timestamp FROM sync_logs ORDER BY timestamp DESC LIMIT 15"):
    print(row)
