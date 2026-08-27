import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin FROM eventos WHERE tecnico_nombre LIKE '%Nicolas%'")
events = c.fetchall()
print('EVENTOS:')
for e in events:
    if str(e[1]) > '2026-08-26':
        print(e)
