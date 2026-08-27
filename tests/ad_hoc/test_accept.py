from data_manager import DataManager
db = DataManager()
with db._get_connection() as c:
    r = c.execute("SELECT review_id FROM poll_review_queue WHERE status='PENDING' LIMIT 1").fetchone()

if r:
    print(f"Probando {r[0]}")
    try:
        db.accept_review(r[0])
        print("EXITO")
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("No pending reviews")
