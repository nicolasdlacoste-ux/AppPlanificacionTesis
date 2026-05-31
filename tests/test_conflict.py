import requests

BASE_URL = "http://localhost:8000"

def test_conflict():
    print("Testing Conflict Validation...")
    
    # Intento de mover un evento a una hora ocupada
    params = {
        "event_id": "TEST_EV_1",
        "calendar_id_origen": "test_cal",
        "correo_destino": "test_cal",
        "nueva_fecha": "2024-05-10",
        "h_start": 9.0,
        "h_dur": 2.0,
        "vehiculo": "Camioneta 1"
    }
    # No hay base de datos cargada f\u00e1cilmente aqui sin levantar el servidor.
    # El servidor est\u00e1 corriendo?
    try:
        res = requests.get(f"{BASE_URL}/api/heartbeat", timeout=2)
        print("Server is UP:", res.json())
        res = requests.patch(f"{BASE_URL}/api/eventos/TEST_EV_1/mover", json=params)
        print(res.status_code, res.text)
    except Exception as e:
        print("Server not reachable or error:", e)

test_conflict()
