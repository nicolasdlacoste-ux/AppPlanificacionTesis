import sys
import json
import urllib.request
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager
from utils import EventAdapter

db = DataManager('planificacion.db')
tecnicos = db.obtener_tecnicos()
raw_events = db.obtener_eventos_dict()
eventos = [EventAdapter.normalize_event(e) for e in raw_events]

# Simular App.js / Scheduler.js lógica
merged = []
for ev in eventos:
    if 'test' in str(ev.get('summary', '')).lower():
        merged.append(ev)

print(f"Total test events in _eventos: {len(merged)}")

for tech in tecnicos:
    tech_nombre = tech.get('nombre')
    tech_correo = tech.get('correo')
    
    # weekEvs logic
    weekEvs = []
    for ev in merged:
        ev_cal = ev.get("calendar_id")
        ev_tec = ev.get("tecnico_nombre")
        
        matchesTech = (ev_cal and ev_cal == tech_correo) or (not ev_cal and ev_tec == tech_nombre)
        if matchesTech:
            weekEvs.append(ev)
            
    if len(weekEvs) > 0:
        print(f"Tech: {tech_nombre} | weekEvs count: {len(weekEvs)}")
        for ev in weekEvs:
            print(f"  - {ev.get('summary')} | cal: {ev.get('calendar_id')}")

