import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin, tecnico_nombre FROM eventos_externos")
events = c.fetchall()
print('EXTERNOS:')
for e in events:
    if 'Nicol' in e[3] and ('2026-08-27' in str(e) or '2026-08-28' in str(e) or '2026-08-26' in str(e) or '2026-08-29' in str(e)):
        print(e)
print('EVENTOS:')
c.execute("SELECT summary, inicio, fin, tecnico_nombre FROM eventos")
events = c.fetchall()
for e in events:
    if 'Nicol' in e[3] and ('2026-08-27' in str(e) or '2026-08-28' in str(e) or '2026-08-26' in str(e) or '2026-08-29' in str(e)):
        print(e)
