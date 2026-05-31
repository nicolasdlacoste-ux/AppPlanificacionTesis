import sqlite3
import json

def check():
    conn = sqlite3.connect('planificacion.db')
    cursor = conn.cursor()
    cursor.execute("SELECT event_type, detail FROM poll_log ORDER BY timestamp DESC LIMIT 20")
    rows = cursor.fetchall()
    for r in rows:
        print(f"{r[0]} | {r[1]}")
    conn.close()

if __name__ == "__main__":
    check()
