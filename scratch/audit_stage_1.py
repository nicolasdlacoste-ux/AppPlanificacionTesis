import sqlite3
import json

def audit_sqlite():
    conn = sqlite3.connect("planificacion.db")
    cursor = conn.cursor()
    
    # 1. Conteo total
    cursor.execute("SELECT COUNT(*) FROM eventos")
    total = cursor.fetchone()[0]
    
    # 2. Conteo por estado
    cursor.execute("SELECT sync_status, COUNT(*) FROM eventos GROUP BY sync_status")
    by_status = cursor.fetchall()
    
    # 3. Muestra de primer evento (raw)
    cursor.execute("SELECT * FROM eventos LIMIT 1")
    row = cursor.fetchone()
    cols = [d[0] for d in cursor.description]
    sample = dict(zip(cols, row)) if row else None
    
    print("--- SQLITE AUDIT ---")
    print(f"Total eventos: {total}")
    print(f"Por estado: {by_status}")
    if sample:
        print(f"Sample Event ID: {sample.get('id')}")
        print(f"Sample Summary: {sample.get('summary')}")
    
    conn.close()

if __name__ == "__main__":
    audit_sqlite()
