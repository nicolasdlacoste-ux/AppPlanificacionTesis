import sqlite3
conn = sqlite3.connect('planificacion.db')
conn.execute("DELETE FROM poll_review_queue WHERE event_id='test-event-001'")
conn.execute("DELETE FROM poll_calendar_state WHERE calendar_id='test@akrimet.com'")
conn.execute("DELETE FROM poll_calendar_state WHERE calendar_id='error@akrimet.com'")
conn.commit()
conn.close()
print("Datos de prueba limpiados.")
