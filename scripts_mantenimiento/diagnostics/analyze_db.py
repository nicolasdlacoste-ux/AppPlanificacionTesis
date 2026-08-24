import sqlite3
import json

def analyze_db():
    db_path = 'planificacion_adeangelis.db'
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        print("=== SYNC_QUEUE ERRORS ===")
        rows = c.execute("SELECT event_id, calendar_id, operation, status, error_msg, created_at FROM sync_queue WHERE status = 'FAILED' ORDER BY rowid DESC LIMIT 10").fetchall()
        print(json.dumps(rows, indent=2))
        
        print("\n=== PENDING EVENTS IN SYNC_QUEUE ===")
        rows2 = c.execute("SELECT event_id, calendar_id, operation, status, error_msg, created_at FROM sync_queue WHERE status != 'DONE' AND status != 'FAILED' ORDER BY rowid DESC LIMIT 10").fetchall()
        print(json.dumps(rows2, indent=2))
        
        print("\n=== RECENT EVENTS IN DB ===")
        rows3 = c.execute("SELECT id, tecnico_nombre, summary, sync_status FROM eventos ORDER BY updated_at DESC LIMIT 5").fetchall()
        print(json.dumps(rows3, indent=2))

    except Exception as e:
        print(f"Error reading DB: {e}")

if __name__ == "__main__":
    analyze_db()
