import sqlite3
import json

db_path = "c:/Users/ndiaz_akrimet/Git Proyect/AppPlanificacion/planificacion.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM cache_patrones LIMIT 1 OFFSET 1")
row = cursor.fetchone()
if row:
    print(row['datos_json'])
