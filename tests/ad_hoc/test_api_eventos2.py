import sys
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager
db = DataManager('planificacion.db')

events = db.obtener_eventos_dict()
print("Total events:", len(events))
for ev in events:
    if 'test 3' in str(ev.get('summary', '')).lower() or 'test 4' in str(ev.get('summary', '')).lower():
        print(f"ID: {ev['id']} | Cal: {ev.get('calendar_id')} | Tec: {ev.get('tecnico_nombre')} | Title: {ev.get('summary')}")
