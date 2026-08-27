import sys
import json
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager
from utils import EventAdapter

db = DataManager('planificacion.db')
raw_events = db.obtener_eventos_dict()
normalized = [EventAdapter.normalize_event(e) for e in raw_events]

for ev in normalized:
    if 'test 3' in str(ev.get('summary', '')).lower() or 'test 4' in str(ev.get('summary', '')).lower():
        print(f"ID: {ev.get('id')} | Cal: {ev.get('calendar_id')} | Start: {ev.get('inicio')} | End: {ev.get('fin')} | Title: {ev.get('summary')}")
