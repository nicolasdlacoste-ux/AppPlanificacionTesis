import sys
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from api_server import poll_manager
import sqlite3

db = sqlite3.connect('planificacion.db')
db.execute("DELETE FROM poll_calendar_state WHERE calendar_id = 'ndiaz@akrimet.com'")
db.commit()

poll_manager._poll_calendar('ndiaz@akrimet.com', 'Nicolas Diaz')
print("Poll triggered")
