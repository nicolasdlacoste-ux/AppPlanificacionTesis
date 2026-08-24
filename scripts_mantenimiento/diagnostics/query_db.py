import sqlite3
c = sqlite3.connect('planificacion.db')
print(c.execute("SELECT id, tecnico_nombre, calendar_id, summary FROM eventos WHERE google_event_id IN ('56f2qi1sch8l852noe22tcj4pe', '6mhr348h1ajluj29v9o5svp7tv')").fetchall())
