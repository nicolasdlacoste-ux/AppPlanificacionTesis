import sqlite3
c = sqlite3.connect('planificacion.db')
print(c.execute("SELECT status FROM poll_review_queue WHERE review_id='a8977145-bb39-436c-b443-7a5178565f3e'").fetchone())
