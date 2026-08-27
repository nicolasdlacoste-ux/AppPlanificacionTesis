import sqlite3
conn = sqlite3.connect('planificador.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin, tecnico_nombre FROM eventos WHERE tecnico_nombre LIKE '%Nicolas%'")
events = c.fetchall()
for e in events:
    if '2026-08-26' in str(e) or '2026-08-27' in str(e) or '2026-08-28' in str(e) or '2026-08-29' in str(e):
        print(e)
