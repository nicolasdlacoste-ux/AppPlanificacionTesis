import sqlite3
db = sqlite3.connect('planificacion.db')
db.row_factory = sqlite3.Row
for r in db.execute("SELECT * FROM tecnicos"):
    print(dict(r))
