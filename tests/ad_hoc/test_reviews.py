import sqlite3
db = sqlite3.connect('planificacion.db')
print("reviews:")
for r in db.execute("SELECT review_id, event_id, status FROM poll_review_queue").fetchall():
    print(r)
