import sqlite3
import json
db = sqlite3.connect('planificacion.db')
db.row_factory = sqlite3.Row
print("review:")
for r in db.execute("SELECT * FROM poll_review_queue WHERE review_id = '4087e106-facf-46e3-907c-c215e3e5eb98'").fetchall():
    print(dict(r))
