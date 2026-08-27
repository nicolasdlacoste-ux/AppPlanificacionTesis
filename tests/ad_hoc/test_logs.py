import sys
import json
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager

db = DataManager('planificacion.db')
with db._get_connection() as conn:
    conn.row_factory = __import__('sqlite3').Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM poll_log WHERE event_type = 'TRACE:FRONTEND_RIGHTPANEL_SHOW_DETAIL' ORDER BY timestamp DESC LIMIT 50")
    rows = cursor.fetchall()
    
    for r in rows:
        d = dict(r)
        detail = d.get('detail')
        if 'test' in str(detail).lower():
            print(f"Log ID: {d['log_id']} | Cal: {d['calendar_id']} | EvID: {d['event_id']}")

