"""
Test end-to-end del sistema de polling.
Verifica: checklist, endpoints, logs, review_queue.
"""
import sys
sys.path.insert(0, '.')
from data_manager import DataManager
from poll_manager import run_pre_polling_checklist, PollingManager

db = DataManager()

print("=" * 60)
print("TEST 1: run_pre_polling_checklist()")
print("=" * 60)
ok = run_pre_polling_checklist(db, sync_worker=None)
print(f"\n>>> Checklist result: {'PASS' if ok else 'FAIL'}")

print()
print("=" * 60)
print("TEST 2: poll_log persistido")
print("=" * 60)
with db._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM poll_log")
    n = cursor.fetchone()[0]
print(f"Entradas en poll_log: {n}")

print()
print("=" * 60)
print("TEST 3: poll_review_queue vacía al inicio")
print("=" * 60)
q = db.get_poll_review_queue()
print(f"Items pendientes: {len(q)}")

print()
print("=" * 60)
print("TEST 4: get_poll_status()")
print("=" * 60)
import json
status = db.get_poll_status()
print(json.dumps(status, indent=2))

print()
print("=" * 60)
print("TEST 5: find_by_google_event_id() — evento existente")
print("=" * 60)
with db._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM eventos LIMIT 1")
    row = cursor.fetchone()

if row:
    sample_id = row[0]
    ev = db.find_by_google_event_id(sample_id)
    if ev:
        print(f"Encontrado: id={ev['id']}, tecnico={ev.get('tecnico_nombre','?')}")
        print(f"  google_event_id={ev.get('google_event_id','?')}")
        print(f"  updated_at={ev.get('updated_at','?')}")
        print(f"  poll_source={ev.get('poll_source','?')}")
    else:
        print("ERROR: evento no encontrado")
else:
    print("No hay eventos en la DB")

print()
print("TEST 6: enqueue_review() + get_poll_review_queue()")
print("=" * 60)
db.enqueue_review(
    event_id    = "test-event-001",
    calendar_id = "test@akrimet.com",
    diff        = {
        "inicio": {"old": "2026-05-06T08:00:00", "new": "2026-05-06T10:00:00", "category": "critical"},
        "fin":    {"old": "2026-05-06T17:00:00", "new": "2026-05-06T19:00:00", "category": "critical"},
    }
)
q = db.get_poll_review_queue()
print(f"Items tras enqueue: {len(q)}")
if q:
    print(f"  event_id={q[0]['event_id']}, calendar_id={q[0]['calendar_id']}")

print()
print("TEST 7: update_last_poll_time() / get_last_poll_time()")
print("=" * 60)
db.update_last_poll_time("test@akrimet.com", "2026-05-06T11:00:00Z")
t = db.get_last_poll_time("test@akrimet.com")
print(f"last_poll_time recuperado: {t}")

print()
print("TEST 8: register_calendar_poll_error()")
print("=" * 60)
db.register_calendar_poll_error("error@akrimet.com", "Connection timeout after 30s")
with db._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT error_count, last_error FROM poll_calendar_state WHERE calendar_id=?",
                   ("error@akrimet.com",))
    r = cursor.fetchone()
    print(f"error_count={r[0]}, last_error='{r[1]}'")

print()
print("=" * 60)
print(">>> TODOS LOS TESTS COMPLETADOS")
print("=" * 60)
