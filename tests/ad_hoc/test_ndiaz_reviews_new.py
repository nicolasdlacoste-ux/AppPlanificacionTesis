import sqlite3
db = sqlite3.connect('planificacion.db')
print("Reviews for test 1:")
for r in db.execute("SELECT review_id, event_id, calendar_id, status FROM poll_review_queue WHERE google_event_id = '5o4lvicj6ok6hvnejollrvuc9c'").fetchall():
    print(r)
