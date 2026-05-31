import sqlite3
conn = sqlite3.connect('planificacion.db')
cursor = conn.cursor()

tables = ['poll_calendar_state', 'poll_log', 'poll_review_queue']
for t in tables:
    cursor.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=? AND name=?', ('table', t))
    n = cursor.fetchone()[0]
    status = 'OK' if n else 'FALTA'
    print(f'tabla {t}: {status}')

cursor.execute('PRAGMA table_info(eventos)')
cols = [c[1] for c in cursor.fetchall()]
print('google_event_id col:', 'OK' if 'google_event_id' in cols else 'FALTA')
print('poll_source col:    ', 'OK' if 'poll_source' in cols else 'FALTA')

cursor.execute('SELECT COUNT(*) FROM eventos WHERE updated_at IS NULL')
nulls = cursor.fetchone()[0]
print(f'updated_at NULLs: {nulls}')

cursor.execute('SELECT COUNT(*) FROM eventos WHERE google_event_id IS NOT NULL')
populated = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM eventos')
total = cursor.fetchone()[0]
print(f'google_event_id poblado: {populated}/{total}')

conn.close()
print('--- Checklist DB completo ---')
