import sqlite3

db = sqlite3.connect('planificacion.db')
db.row_factory = sqlite3.Row

print("Eventos con 'test 3' o 'test 4':")
cursor = db.execute("SELECT id, summary, tecnico_nombre, calendar_id FROM eventos WHERE summary LIKE '%test 3%' OR summary LIKE '%test 4%'")
for r in cursor.fetchall():
    print(dict(r))

print("\nReviews con 'test 3' o 'test 4':")
cursor = db.execute("SELECT review_id, event_id, calendar_id, status FROM poll_review_queue WHERE diff LIKE '%test 3%' OR diff LIKE '%test 4%'")
for r in cursor.fetchall():
    print(dict(r))
