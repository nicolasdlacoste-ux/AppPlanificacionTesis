import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT DISTINCT tecnico_nombre FROM eventos")
print("EVENTOS:", [r[0] for r in c.fetchall()])
c.execute("SELECT DISTINCT tecnico_nombre FROM eventos_externos")
print("EXTERNOS:", [r[0] for r in c.fetchall()])
