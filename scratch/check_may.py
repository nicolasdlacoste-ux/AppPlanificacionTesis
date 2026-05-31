import sqlite3

db_path = "planificacion.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM eventos WHERE inicio LIKE '2026-05-%'")
may_count = cursor.fetchone()[0]

cursor.execute("SELECT inicio, summary FROM eventos WHERE inicio LIKE '2026-05-%' LIMIT 5")
may_samples = cursor.fetchall()

print(f"Eventos en Mayo 2026: {may_count}")
for row in may_samples:
    print(row)

conn.close()
