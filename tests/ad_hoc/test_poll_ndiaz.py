import sqlite3
db = sqlite3.connect('planificacion.db')
print("poll state:", db.execute("SELECT * FROM poll_calendar_state WHERE calendar_id = 'ndiaz@akrimet.com'").fetchone())
