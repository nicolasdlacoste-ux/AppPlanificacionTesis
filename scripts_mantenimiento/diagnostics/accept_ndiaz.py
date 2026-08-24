import sys
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager
import sqlite3

db = DataManager('planificacion.db')

pending = db.get_poll_review_queue()
for r in pending:
    db.accept_review(r['review_id'])
    print("Accepted:", r['review_id'])

print("Done")
