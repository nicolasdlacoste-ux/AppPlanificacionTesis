import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin FROM eventos WHERE tecnico_nombre LIKE '%Nicolas%'")
events = c.fetchall()
for e in events:
    print(e)
