import sqlite3
import json
import sys

def query(search_term):
    conn = sqlite3.connect('planificacion.db')
    cursor = conn.cursor()
    cursor.execute("SELECT event_type, detail FROM poll_log WHERE detail LIKE ? ORDER BY timestamp DESC", (f'%{search_term}%',))
    rows = cursor.fetchall()
    for et, detail in rows:
        print(f"[{et}] {detail[:200]}...")
    conn.close()

if __name__ == "__main__":
    query(sys.argv[1])
