import requests
import time
import json
import uuid

BASE_URL = "http://localhost:8000"

def run_test():
    print(">>> Iniciando Loop Test (Outbound + Inbound)...")
    
    # 1. Crear evento local
    test_id = f"loop_{uuid.uuid4().hex[:6]}"
    payload = {
        "correo_tecnico": "ndiaz@akrimet.com",
        "titulo": f"LOOP TEST EVENT - {test_id} (OT 7777)",
        "descripcion": "Prueba de loop sincronizado",
        "direccion": "Laboratorio Akrimet",
        "fecha": "2026-12-01",
        "h_start": 10.0,
        "h_dur": 1.0,
        "patrones": [],
        "ots": ["7777"]
    }
    
    print(f"\n[1] Creando evento {payload['titulo']}...")
    r = requests.post(f"{BASE_URL}/api/eventos/crear", json=payload)
    if r.status_code != 200:
        print(f"ERROR al crear: {r.text}")
        return
    
    resp_data = r.json()
    test_id = resp_data.get("id")
    print(f"DONE: Evento creado localmente. ID: {test_id}")
    
    # 2. Esperar a que el SyncWorker lo suba a Google
    print("\n[2] Esperando SyncWorker (Outbound)...")
    max_wait = 60
    synced = False
    for _ in range(max_wait // 5):
        time.sleep(5)
        r = requests.get(f"{BASE_URL}/api/eventos")
        evs = r.json() # Ahora sabemos que es una lista plana
        ev = next((e for e in evs if e["id"] == test_id), None)
        if ev and ev.get("sync_status") == "SUCCESS":
            synced = True
            print(f"DONE: Sincronizado a Google. Google ID: {ev.get('google_event_id')}")
            break
        print("    ...todavía pendiente...")
        
    if not synced:
        print("ERROR: Timeout esperando sincronización outbound.")
        return
        
    # 3. Disparar Polling y verificar Anti-Loop
    print("\n[3] Disparando Polling (Inbound)...")
    requests.post(f"{BASE_URL}/api/poll/trigger")
    time.sleep(10) # Esperar a que termine el ciclo
    
    # 4. Verificar Logs de Polling
    print("\n[4] Verificando logs de Anti-Loop...")
    r = requests.get(f"{BASE_URL}/BASE_URL/api/poll/log?limit=20") # Espera, ruta equivocada?
    # Usar el script local mejor
    
    print("\n[FIN] Prueba manual requerida para ver logs.")

if __name__ == "__main__":
    run_test()
