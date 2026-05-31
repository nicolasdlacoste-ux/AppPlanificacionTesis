import requests
import time
import sqlite3
from extractor import _safe_get_google_services

BASE_URL = "http://localhost:8000"

def run_test():
    print(">>> Iniciando Test de Reconciliación de Borrado...")
    
    # 1. Buscar un evento con google_event_id real
    conn = sqlite3.connect('planificacion.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, google_event_id, calendar_id, summary FROM eventos WHERE google_event_id NOT LIKE 'local_%' LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print("ERROR: No se encontró ningún evento con Google ID real.")
        return
        
    local_id, google_id, cal_id, summary = row
    print(f"Evento objetivo: {summary} (ID: {local_id}, Google ID: {google_id})")
    
    # 2. Borrar en Google (usando el servicio directamente para simular cambio externo)
    print(f"[1] Borrando en Google (Calendar: {cal_id})...")
    svc_cal, _ = _safe_get_google_services()
    try:
        svc_cal.events().delete(calendarId=cal_id, eventId=google_id).execute()
        print("DONE: Borrado en Google.")
    except Exception as e:
        print(f"ERROR al borrar en Google: {e}")
        return
        
    # 3. Disparar Polling
    print("\n[2] Disparando Polling...")
    requests.post(f"{BASE_URL}/api/poll/trigger")
    time.sleep(10)
    
    # 4. Verificar estado en DB
    print("\n[3] Verificando reconciliación en SQLite...")
    conn = sqlite3.connect('planificacion.db')
    cursor = conn.cursor()
    cursor.execute("SELECT extended_props FROM eventos WHERE id=?", (local_id,))
    props_str = cursor.fetchone()[0]
    conn.close()
    
    import json
    props = json.loads(props_str)
    state = props.get("private", {}).get("sync_state")
    
    if state == "CANCELLED_IN_GOOGLE":
        print(f"SUCCESS: Evento marcado correctamente como {state}")
    else:
        print(f"FAILURE: Estado esperado CANCELLED_IN_GOOGLE, pero es {state}")

if __name__ == "__main__":
    run_test()
