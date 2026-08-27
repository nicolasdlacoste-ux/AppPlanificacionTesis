import sqlite3
db = sqlite3.connect('planificacion.db')
for r in db.execute("SELECT id, summary, tecnico_nombre, calendar_id FROM eventos WHERE summary LIKE '%6160%'").fetchall():
    print(r)
