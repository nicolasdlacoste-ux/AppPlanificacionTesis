import sys
import json
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager

db = DataManager('planificacion.db')
with db._get_connection() as conn:
    conn.row_factory = __import__('sqlite3').Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos WHERE summary LIKE '%test 3%' OR summary LIKE '%test 4%'")
    rows = cursor.fetchall()
    
    for r in rows:
        d = dict(r)
        print(f"ID: {d['id']} | Cal: {d['calendar_id']} | sync_state: {d['sync_state']} | sync_status: {d['sync_status']} | Title: {d['summary']}")

