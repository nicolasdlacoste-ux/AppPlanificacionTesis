import sys
import json
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from api_server import app
from fastapi.testclient import TestClient

client = TestClient(app)

response = client.get("/api/eventos")
events = response.json()

print("Total events:", len(events))
for ev in events:
    if 'test 3' in str(ev.get('summary', '')).lower() or 'test 4' in str(ev.get('summary', '')).lower():
        print(f"Found event: {ev['summary']} - {ev.get('tecnico_nombre')} - ID: {ev['id']}")
