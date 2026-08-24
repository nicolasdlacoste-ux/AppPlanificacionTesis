import sqlite3
import json
c = sqlite3.connect('planificacion.db')
c.row_factory = sqlite3.Row

print("Eventos totales:", c.execute('SELECT COUNT(*) FROM eventos').fetchone()[0])
print("Reviews recientes:", c.execute('SELECT COUNT(*) FROM poll_review_queue WHERE detected_at > "2026-06-05"').fetchone()[0])

eventos = [dict(r) for r in c.execute('SELECT id, google_event_id, summary, tecnico_nombre, calendar_id FROM eventos WHERE summary LIKE "%6160%" OR summary LIKE "%8419%" OR summary LIKE "%9088%" OR summary LIKE "%9104%"').fetchall()]
print(json.dumps(eventos, indent=2))
