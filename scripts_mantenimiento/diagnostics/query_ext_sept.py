import sqlite3
conn = sqlite3.connect('planificacion.db')
c = conn.cursor()
c.execute("SELECT summary, inicio, fin, tecnico_nombre FROM eventos_externos")
events = c.fetchall()
print('EXTERNOS:')
for e in events:
    if 'Nicol' in e[3] and ('2026-08-31' in str(e) or '2026-09-01' in str(e) or '2026-09-02' in str(e)):
        print(e)
