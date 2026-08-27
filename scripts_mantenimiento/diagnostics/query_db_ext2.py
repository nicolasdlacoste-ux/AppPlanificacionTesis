import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin, tecnico_nombre FROM eventos_externos WHERE tecnico_nombre LIKE '%Nicolas%'")
events = c.fetchall()
print(f'Found {len(events)} external events for Nicolas')
for e in events[:15]:
    print(e)
