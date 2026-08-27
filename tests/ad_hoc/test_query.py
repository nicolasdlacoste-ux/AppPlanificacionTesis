import sqlite3
import json

db = sqlite3.connect('planificacion.db')
db.row_factory = sqlite3.Row
rows = db.execute("SELECT summary, extended_props FROM eventos WHERE summary LIKE '%8419 (ASSERCA)%'").fetchall()
for r in rows:
    print(r['summary'])
    print(json.loads(r['extended_props']).get('private', {}).get('has_guests'))
