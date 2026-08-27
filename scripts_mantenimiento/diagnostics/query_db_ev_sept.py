import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin FROM eventos WHERE tecnico_nombre LIKE '%Nicolas%'")
events = c.fetchall()
print('EVENTOS:')
for e in events:
    if any(date in str(e) for date in ['2026-08-31', '2026-09-01', '2026-09-02']):
        print(e)
