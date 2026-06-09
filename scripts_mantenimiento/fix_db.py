import sqlite3

c = sqlite3.connect('planificacion.db')
c.execute("UPDATE eventos SET sync_state='CANCELLED_IN_GOOGLE', sync_status='SUCCESS' WHERE sync_status='CANCELLED_IN_GOOGLE'")
c.commit()
print("Fixed corrupted DB entries.")
