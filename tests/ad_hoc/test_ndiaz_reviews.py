import sqlite3
db = sqlite3.connect('planificacion.db')
print("ndiaz reviews:")
for r in db.execute("SELECT review_id, event_id, status FROM poll_review_queue WHERE calendar_id = 'ndiaz@akrimet.com' AND event_id IN ('5o4lvicj6ok6hvnejollrvuc9c', '0lemlhkggbk89i1flrq4801v7k')").fetchall():
    print(r)
print("lrivera reviews:")
for r in db.execute("SELECT review_id, event_id, status FROM poll_review_queue WHERE calendar_id = 'lrivera@akrimet.com' AND event_id IN ('5o4lvicj6ok6hvnejollrvuc9c', '0lemlhkggbk89i1flrq4801v7k')").fetchall():
    print(r)
