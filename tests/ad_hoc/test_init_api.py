import sys
import json
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager

db = DataManager('planificacion.db')
print(json.dumps(db.obtener_tecnicos(), indent=2))
